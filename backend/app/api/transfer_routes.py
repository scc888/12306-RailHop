"""Read-only transfer station and journey APIs."""
from datetime import datetime
from threading import Lock
from fastapi import APIRouter, Depends, HTTPException, Query
from ..models.schemas import ApiResponse
from ..models.transfer_schemas import TransferQueryRequest, TransferSearchResult, TransferStation
from ..services.station_service import station_service
from ..services.transfer_station_service import TransferStationService
from ..services.transfer_ticket_gateway import TransferTicketGateway
from ..services.transfer_planner import TransferPlanner

router = APIRouter(prefix='/api/transfers', tags=['同站中转查询'])
transfer_stations = TransferStationService()
transfer_planner = TransferPlanner(transfer_stations, TransferTicketGateway())
transfer_lock = Lock()


def get_transfer_planner():
    return transfer_planner


@router.get('/stations', response_model=ApiResponse[list[TransferStation]])
def search_stations(keyword: str = Query('', max_length=50), limit: int = Query(20, ge=1, le=100)):
    return ApiResponse(data=transfer_stations.search(keyword, limit))


@router.post('/query', response_model=ApiResponse[TransferSearchResult])
def query_transfers(request: TransferQueryRequest, planner=Depends(get_transfer_planner)):
    if not transfer_lock.acquire(blocking=False):
        raise HTTPException(429, '当前有中转查询正在进行，请稍后重试', headers={'Retry-After': '5'})
    try:
        station_service.ensure_loaded()
        if any(code not in station_service.code_to_name for code in (request.from_station, request.to_station)):
            raise ValueError('无法识别出发站或到达站，请从站点列表选择')
        return ApiResponse(data=planner.search(request))
    except (ValueError, OverflowError) as exc:
        raise HTTPException(400, str(exc) if isinstance(exc, ValueError) else '乘车日期超出支持范围') from exc
    finally:
        transfer_lock.release()
