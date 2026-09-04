import uvicorn


def main() -> None:
    uvicorn.run("storytube.web.main:app", host="127.0.0.1", port=8420, reload=False)


if __name__ == "__main__":
    main()
