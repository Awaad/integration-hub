import random
from app.connectors.base import PublishResult

class MockDestinationConnector:
    key = "mock"

    async def publish_listing(self, listing: dict, credentials: dict) -> PublishResult:
        # Simulate occasional failures
        if listing.get("payload", {}).get("title") == "FAIL":
            return PublishResult(ok=False, error_code="MOCK_FAIL", error_message="forced fail", retryable=True)

        if random.random() < 0.1:
            return PublishResult(ok=False, error_code="MOCK_TEMP", error_message="temporary error", retryable=True)

        return PublishResult(ok=True, external_id=f"ext_{listing['id']}", detail={"mock": True})
