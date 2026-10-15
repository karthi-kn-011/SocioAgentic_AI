import sys
import uvicorn
from backend.app.config import settings

def main():
    print(f"================================================================")
    print(f"  {settings.APP_NAME} v1.0.0")
    print(f"  Environment : {settings.ENVIRONMENT}")
    print(f"  Database    : {settings.DATABASE_URL.split('://')[0]}")
    print(f"  Mock Mode   : Social={settings.MOCK_SOCIAL_PUBLISHING}, Slack={settings.SLACK_MOCK_MODE}")
    print(f"  Listening   : http://{settings.HOST}:{settings.PORT}")
    print(f"  API Docs    : http://{settings.HOST}:{settings.PORT}/docs")
    print(f"================================================================")

    uvicorn.run(
        "backend.app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info"
    )

if __name__ == "__main__":
    main()
