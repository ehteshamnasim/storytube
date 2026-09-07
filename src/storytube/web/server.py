import uvicorn

from .. import config


def main() -> None:
    uvicorn.run("storytube.web.main:app", host="127.0.0.1", port=config.WEB_PORT, reload=False)


if __name__ == "__main__":
    main()

