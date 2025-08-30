from dotenv import load_dotenv
load_dotenv()

import asyncio
from macats.orchestrator import main as orchestrator_main

if __name__ == "__main__":
    asyncio.run(orchestrator_main())