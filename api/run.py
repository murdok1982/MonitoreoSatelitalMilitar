"""Run the AEGIS-IMINT API server."""
import uvicorn
import os

if __name__ == '__main__':
    port = int(os.getenv('API_PORT', '8502'))
    reload = os.getenv('API_RELOAD', '0') == '1'
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info",
    )
