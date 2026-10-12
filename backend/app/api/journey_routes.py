"""Read-only journey search, sharing the bounded planner's concurrency guard."""
from fastapi import APIRouter, Depends, HTTPException
from ..models.schemas import ApiResponse
from ..models.journey_schemas import JourneyQueryRequest, JourneyResult
from ..services.client_12306 import Ticket12306Client
from ..services.station_service import station_service
from ..services.smart_planner import smart_planner
from ..services.journey_service import JourneyService
from .transfer_routes import transfer_lock, transfer_planner

router=APIRouter(prefix='/api/journeys',tags=['城市出行查询'])
journey_service=JourneyService(Ticket12306Client(),station_service,smart_planner,transfer_planner)


def get_journey_service():
    return journey_service


@router.post('/query',response_model=ApiResponse[JourneyResult])
def query_journey(request:JourneyQueryRequest, service=Depends(get_journey_service)):
    if not transfer_lock.acquire(blocking=False):
        raise HTTPException(429,'当前有路线查询正在进行，请稍后重试',headers={'Retry-After':'5'})
    try:
        return ApiResponse(data=service.search(request))
    except (ValueError,OverflowError) as exc:
        raise HTTPException(400,str(exc) if isinstance(exc,ValueError) else '日期超出支持范围') from exc
    finally:
        transfer_lock.release()
