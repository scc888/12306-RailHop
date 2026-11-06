"""Read-only journey search with independent per-request planning state."""
from fastapi import APIRouter, Depends, HTTPException
from ..models.schemas import ApiResponse
from ..models.journey_schemas import JourneyQueryRequest, JourneyResult
from ..services.client_12306 import Ticket12306Client, register_active_search, unregister_active_search
from ..services.station_service import station_service
from ..services.smart_planner import SmartRoutePlanner
from ..services.journey_service import JourneyService
from ..services.transfer_planner import TransferPlanner
from ..services.transfer_ticket_gateway import TransferTicketGateway
from ..services.query_cache import query_cache
from .transfer_routes import transfer_stations

router=APIRouter(prefix='/api/journeys',tags=['城市出行查询'])


def get_journey_service():
    client = Ticket12306Client(cache=query_cache)
    try:
        planner = TransferPlanner(transfer_stations, TransferTicketGateway(client))
        yield JourneyService(client, station_service, SmartRoutePlanner(client), planner)
    finally:
        client.session.close()


@router.post('/query',response_model=ApiResponse[JourneyResult])
def query_journey(request:JourneyQueryRequest, service=Depends(get_journey_service)):
    event, token = register_active_search()
    try:
        return ApiResponse(data=service.search(request))
    except (ValueError,OverflowError) as exc:
        raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else '日期超出支持范围') from exc
    finally:
        unregister_active_search(event, token)
