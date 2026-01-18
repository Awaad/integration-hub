from app.destinations.registry import register
from app.destinations.evler101.connector import Evler101HostedFeedConnector

register(Evler101HostedFeedConnector())
