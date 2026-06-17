from fastapi import FastAPI


def create_mobile_app(
    on_command,
    list_tasks,
    upload_dir,
    get_health,
    on_mic_toggle,
    on_restart,
) -> FastAPI:
    app = FastAPI(title="JASS Mobile Sync")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def run_uvicorn_thread(app, host="0.0.0.0", port=8756):
    return None, None
