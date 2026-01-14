from app.connectors.mock import MockDestinationConnector

CONNECTORS = {
    MockDestinationConnector.key: MockDestinationConnector(),
}

def get_connector(destination: str):
    if destination not in CONNECTORS:
        raise KeyError(f"Unknown destination: {destination}")
    return CONNECTORS[destination]
