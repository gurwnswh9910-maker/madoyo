import os
import sys
import logging
from celery import Celery
from dotenv import load_dotenv
from api.logging_utils import get_logger, log_event, preview_text

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "copy_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
)

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

logger = get_logger(__name__)


def _format_results(results):
    formatted_copies = []
    for index, result in enumerate(results or []):
        formatted_copies.append(
            {
                "rank": index + 1,
                "copy_text": result.get("copy", ""),
                "strategy": result.get("strategy", "strategy"),
                "score": result.get("score_data", {}).get("mss_score_estimate", 0),
                "reason": result.get("score_data", {}).get("reason", ""),
            }
        )
    return formatted_copies


@celery_app.task(name="optimize_copy_task", bind=True)
def optimize_copy_task(
    self,
    reference_copy=None,
    image_urls=None,
    reference_url=None,
    appeal_point=None,
    api_key=None,
    model_name=None,
    user_id=None,
    generation_id=None,
    request_id=None,
):
    """Run copy optimization in a background worker."""
    log_event(
        logger,
        logging.INFO,
        "worker.optimize_copy.started",
        task_id=self.request.id,
        user_id=user_id,
        generation_id=generation_id,
        request_id=request_id or generation_id or self.request.id,
        has_reference_copy=bool(reference_copy),
        image_count=len(image_urls or []),
        has_reference_url=bool(reference_url),
    )

    from optimize_copy_v2 import run_optimization
    from api.services.context_builder import build_context

    self.update_state(state="PROGRESS", meta={"status": "Building context..."})

    try:
        product_focus, original_copy = build_context(
            api_key=api_key,
            model_name=model_name,
            reference_copy=reference_copy,
            image_urls=image_urls,
            reference_url=reference_url,
            appeal_point=appeal_point,
        )
        log_event(
            logger,
            logging.INFO,
            "worker.optimize_copy.context_built",
            task_id=self.request.id,
            generation_id=generation_id,
            request_id=request_id or generation_id or self.request.id,
            product_focus_type=type(product_focus).__name__,
            original_copy_preview=preview_text(original_copy, limit=80),
        )

        if not original_copy or not original_copy.strip():
            if isinstance(product_focus, dict):
                original_copy = product_focus.get("marketing_insight", "product marketing copy")
            else:
                original_copy = str(product_focus)

        self.update_state(state="PROGRESS", meta={"status": "Running optimization..."})
        results = run_optimization(
            original_copy=original_copy,
            product_focus=product_focus,
            api_key=api_key,
            model_name=model_name,
            user_id=user_id,
        )
        log_event(
            logger,
            logging.INFO,
            "worker.optimize_copy.completed",
            task_id=self.request.id,
            generation_id=generation_id,
            request_id=request_id or generation_id or self.request.id,
            result_count=len(results or []),
        )

        return {"status": "SUCCESS", "results": {"copies": _format_results(results)}}
    except Exception as error:
        logger.exception(
            "worker.optimize_copy.failed | task_id=%r generation_id=%r request_id=%r user_id=%r",
            self.request.id,
            generation_id,
            request_id or generation_id or self.request.id,
            user_id,
        )
        import traceback

        error_message = f"Worker optimize_copy failed: {error}\n{traceback.format_exc()}"
        print(error_message)
        return {"status": "FAILED", "error": str(error)}


@celery_app.task(name="process_excel_task", bind=True)
def process_excel_task(self, file_path, uploader_id=None, is_global=True, bulk_job_id=None):
    """Load a spreadsheet, discover URL rows, and fan out worker tasks."""
    import pandas as pd
    import uuid as uuid_pkg

    log_event(
        logger,
        logging.INFO,
        "worker.process_excel.started",
        task_id=self.request.id,
        bulk_job_id=bulk_job_id,
        uploader_id=uploader_id,
        file_path=preview_text(file_path, limit=120),
    )
    print(f"[Worker] Starting process_excel_task for {file_path}, Job: {bulk_job_id}")

    try:
        if file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        print(f"[Worker] File loaded. Rows: {len(df)}, Columns: {df.columns.tolist()}")
        log_event(
            logger,
            logging.INFO,
            "worker.process_excel.loaded",
            task_id=self.request.id,
            row_count=len(df),
            column_count=len(df.columns),
        )

        url_col = None
        for col in df.columns:
            column_name = str(col).lower()
            if "link" in column_name or "url" in column_name:
                url_col = col
                break

        if url_col:
            urls_to_process = df[url_col].dropna().tolist()
            print(f"[Worker] Found {len(urls_to_process)} URLs in column '{url_col}'")
            log_event(
                logger,
                logging.INFO,
                "worker.process_excel.urls_found",
                task_id=self.request.id,
                url_count=len(urls_to_process),
                url_column=str(url_col),
            )
        else:
            log_event(
                logger,
                logging.WARNING,
                "worker.process_excel.url_column_missing",
                task_id=self.request.id,
                columns=[str(column) for column in df.columns],
            )
            print("[Worker] FAILED: No link or URL column found.")
            return {"status": "FAILED", "error": "No link or URL column found in uploaded file."}

        from api.database import SessionLocal, Generation

        db = SessionLocal()
        try:
            user_uuid = None
            if uploader_id:
                try:
                    user_uuid = uuid_pkg.UUID(uploader_id)
                except Exception:
                    user_uuid = uploader_id

            for url in urls_to_process:
                url_str = str(url).strip()
                if "http" not in url_str:
                    continue

                generation = Generation(
                    bulk_job_id=bulk_job_id,
                    user_id=user_uuid,
                    input_config={"url": url_str, "scraped_text": "Pending scrape..."},
                    results={},
                    status="pending",
                )
                db.add(generation)
                db.commit()
                db.refresh(generation)
                print(f"[Worker] Inserted pending generation for {url_str}, GenID: {generation.id}")

                scrape_and_generate_single_task.delay(
                    url=url_str,
                    bulk_job_id=bulk_job_id,
                    uploader_id=uploader_id,
                    is_global=is_global,
                    generation_id=str(generation.id),
                )
        finally:
            db.close()

        if os.path.exists(file_path):
            os.remove(file_path)

        log_event(
            logger,
            logging.INFO,
            "worker.process_excel.completed",
            task_id=self.request.id,
            spawned_tasks=len(urls_to_process),
        )
        return {"status": "SUCCESS", "spawned_tasks": len(urls_to_process)}
    except Exception as error:
        logger.exception("worker.process_excel.failed | task_id=%r bulk_job_id=%r", self.request.id, bulk_job_id)
        return {"status": "FAILED", "error": str(error)}


@celery_app.task(name="scrape_and_generate_single_task", bind=True)
def scrape_and_generate_single_task(self, url, bulk_job_id, uploader_id=None, is_global=True, generation_id=None):
    """Scrape one URL, learn from it, and generate copy suggestions."""
    import uuid as uuid_pkg

    log_event(
        logger,
        logging.INFO,
        "worker.scrape_generate.started",
        task_id=self.request.id,
        generation_id=generation_id,
        bulk_job_id=bulk_job_id,
        url=preview_text(url, limit=120),
    )
    print(f"[Worker] Submitting task for {url}, GenID: {generation_id}")

    from api.database import SessionLocal, MABEmbedding, Generation
    from embedding_utils import EmbeddingManager
    from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics
    from optimize_copy_v2 import run_optimization
    from api.config import GEMINI_API_KEY, MODEL_NAME
    from google import genai
    from marketing_focus_extractor import extract_marketing_focus

    db = SessionLocal()
    emb_mgr = EmbeddingManager()

    try:
        data = get_threads_full_data(url)
        if not data or not data.get("content_text"):
            log_event(
                logger,
                logging.WARNING,
                "worker.scrape_generate.scrape_empty",
                task_id=self.request.id,
                generation_id=generation_id,
            )
            if generation_id:
                gid = uuid_pkg.UUID(generation_id) if isinstance(generation_id, str) else generation_id
                generation = db.query(Generation).filter(Generation.id == gid).first()
                if generation:
                    generation.input_config = {"url": url, "scraped_text": "Scrape failed: content text not found."}
                    generation.status = "error"
                    db.commit()
            return {"status": "FAILED", "error": "No scraped text was found for the URL."}

        content_text = data["content_text"]
        mss = calculate_mss_from_metrics(data)
        log_event(
            logger,
            logging.INFO,
            "worker.scrape_generate.scrape_completed",
            task_id=self.request.id,
            generation_id=generation_id,
            mss=mss,
        )

        vector = emb_mgr.get_text_embedding(content_text)
        new_entry = MABEmbedding(
            content_text=content_text,
            embedding_type="text",
            mss_score=mss,
            embedding=vector,
            uploader_id=uploader_id,
            is_global=is_global,
            metadata_json={"source": "url_bulk", "url": url, "metrics": data},
        )
        db.add(new_entry)
        db.commit()

        print(f"[Worker] Extracting marketing focus for {url}...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        product_focus = extract_marketing_focus(
            client=client,
            model_name=MODEL_NAME,
            product_name="product",
            original_text=content_text,
            threads_images=data.get("image_urls", []),
        )
        log_event(
            logger,
            logging.INFO,
            "worker.scrape_generate.focus_completed",
            task_id=self.request.id,
            generation_id=generation_id,
        )

        results = run_optimization(
            original_copy=content_text,
            product_focus=product_focus,
            api_key=GEMINI_API_KEY,
            model_name=MODEL_NAME,
            user_id=uploader_id,
        )
        log_event(
            logger,
            logging.INFO,
            "worker.scrape_generate.optimization_completed",
            task_id=self.request.id,
            generation_id=generation_id,
            result_count=len(results or []),
        )

        formatted_copies = _format_results(results)

        if generation_id:
            gid = uuid_pkg.UUID(generation_id) if isinstance(generation_id, str) else generation_id
            generation = db.query(Generation).filter(Generation.id == gid).first()
            if generation:
                print(f"[Worker] Updating Generation record {gid} to completed")
                generation.input_config = {"url": url, "scraped_text": content_text[:100]}
                generation.results = {"copies": formatted_copies}
                generation.status = "completed"
                db.commit()
                log_event(
                    logger,
                    logging.INFO,
                    "worker.scrape_generate.completed",
                    task_id=self.request.id,
                    generation_id=generation_id,
                    mode="existing_generation",
                )
                return {"status": "SUCCESS", "url": url}

        user_uuid = None
        if uploader_id:
            try:
                user_uuid = uuid_pkg.UUID(uploader_id) if isinstance(uploader_id, str) else uploader_id
            except Exception:
                user_uuid = uploader_id

        generation = Generation(
            bulk_job_id=bulk_job_id,
            user_id=user_uuid,
            input_config={"url": url, "scraped_text": content_text[:100]},
            results={"copies": formatted_copies},
            status="completed",
        )
        db.add(generation)
        db.commit()
        print(f"[Worker] Success (Fallback ID used) for {url}")
        log_event(
            logger,
            logging.INFO,
            "worker.scrape_generate.completed",
            task_id=self.request.id,
            generation_id=generation_id,
            mode="fallback_generation",
        )
        return {"status": "SUCCESS", "url": url}
    except Exception as error:
        db.rollback()
        logger.exception("worker.scrape_generate.failed | task_id=%r generation_id=%r url=%r", self.request.id, generation_id, url)
        return {"status": "FAILED", "error": str(error)}
    finally:
        db.close()


@celery_app.task(name="update_post_performance_task", bind=True)
def update_post_performance_task(self, url, feedback_id):
    """Refresh post performance and grant reward credits when applicable."""
    log_event(
        logger,
        logging.INFO,
        "worker.update_performance.started",
        task_id=self.request.id,
        feedback_id=feedback_id,
        url=preview_text(url, limit=120),
    )

    from api.database import SessionLocal, MABFeedback, MABEmbedding, User, Generation
    from embedding_utils import EmbeddingManager
    from api.services.scraper_service import get_threads_full_data, calculate_mss_from_metrics

    db = SessionLocal()
    emb_mgr = EmbeddingManager()

    try:
        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == feedback_id).first()
        if not feedback:
            log_event(
                logger,
                logging.WARNING,
                "worker.update_performance.feedback_missing",
                task_id=self.request.id,
                feedback_id=feedback_id,
            )
            return "Feedback entry not found"

        if feedback.status != "pending":
            log_event(
                logger,
                logging.INFO,
                "worker.update_performance.skipped",
                task_id=self.request.id,
                feedback_id=feedback_id,
                status=feedback.status,
            )
            return f"Feedback already processed: {feedback.status}"

        data = get_threads_full_data(url)
        if not data or not data.get("content_text"):
            feedback.status = "rejected"
            db.commit()
            log_event(
                logger,
                logging.WARNING,
                "worker.update_performance.scrape_empty",
                task_id=self.request.id,
                feedback_id=feedback_id,
            )
            return "No data scraped or post deleted"

        mss = calculate_mss_from_metrics(data)
        content_text = data["content_text"]

        vector = emb_mgr.get_text_embedding(content_text)
        entry = MABEmbedding(
            content_text=content_text,
            embedding_type="text",
            mss_score=mss,
            embedding=vector,
            is_global=True,
            metadata_json={"source": "feedback_reward", "url": url, "metrics": data},
        )
        db.add(entry)

        feedback.performance = data
        feedback.status = "completed"
        feedback.reward_credits = 2

        generation = db.query(Generation).filter(Generation.id == feedback_id).first()
        if generation and generation.user_id:
            user = db.query(User).filter(User.id == generation.user_id).first()
            if user:
                user.credits += feedback.reward_credits

        db.commit()
        log_event(
            logger,
            logging.INFO,
            "worker.update_performance.completed",
            task_id=self.request.id,
            feedback_id=feedback_id,
            mss=mss,
            reward_credits=feedback.reward_credits,
        )
        return f"Success: {url} -> Given 2 credits, MSS: {mss}"
    except Exception as error:
        db.rollback()
        logger.exception("worker.update_performance.failed | task_id=%r feedback_id=%r url=%r", self.request.id, feedback_id, url)
        from api.database import MABFeedback

        feedback = db.query(MABFeedback).filter(MABFeedback.gen_id == feedback_id).first()
        if feedback:
            feedback.status = "error"
            db.commit()
        return f"Error: {error}"
    finally:
        db.close()
