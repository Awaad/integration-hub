from app.destinations.registry import register
from app.destinations.evler101.connector import Evler101HostedFeedConnector
from app.destinations.mls_demo_push.connector import DemoPushConnector

register(Evler101HostedFeedConnector())
register(DemoPushConnector())