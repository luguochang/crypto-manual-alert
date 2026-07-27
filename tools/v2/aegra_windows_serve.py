import argparse
import asyncio

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    config = uvicorn.Config(
        "aegra_api.main:app",
        host=args.host,
        port=args.port,
        loop=asyncio.SelectorEventLoop,
    )
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
