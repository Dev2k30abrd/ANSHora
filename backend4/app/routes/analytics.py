from fastapi import APIRouter, HTTPException

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.tools.analytics_tools import (
    get_basic_statistics,
    get_column_analysis,
    group_analysis,
    correlation_analysis,
    missing_value_report,
    outlier_detection,
    distribution_analysis,
    pivot_table_analysis,
    trend_analysis,
    top_n_analysis,
    filter_analysis,
    full_eda_summary,
)


router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


def _load(dataset_id: str):
    try:
        return dataset_store.get(dataset_id)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.get("/statistics")
def basic_statistics(dataset_id: str):
    try:
        return get_basic_statistics(_load(dataset_id))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/column/{column_name}")
def analyze_column(column_name: str, dataset_id: str):
    try:
        return get_column_analysis(_load(dataset_id), column_name)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/group")
def analyze_group(dataset_id: str, group_column: str, value_column: str, operation: str = "sum"):
    try:
        return group_analysis(_load(dataset_id), group_column, value_column, operation)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/correlation")
def analyze_correlation(dataset_id: str):
    try:
        return correlation_analysis(_load(dataset_id))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/missing")
def analyze_missing(dataset_id: str):
    try:
        return missing_value_report(_load(dataset_id))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/outliers")
def analyze_outliers(dataset_id: str, column: str | None = None):
    try:
        return outlier_detection(_load(dataset_id), column)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/distribution/{column_name}")
def analyze_distribution(column_name: str, dataset_id: str, bins: int = 10):
    try:
        return distribution_analysis(_load(dataset_id), column_name, bins)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/pivot")
def analyze_pivot(
    dataset_id: str, index: str, values: str, columns: str | None = None, aggfunc: str = "sum"
):
    try:
        return pivot_table_analysis(_load(dataset_id), index, values, columns, aggfunc)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/trend")
def analyze_trend(dataset_id: str, date_column: str, value_column: str, freq: str = "M"):
    try:
        return trend_analysis(_load(dataset_id), date_column, value_column, freq)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/top")
def analyze_top(dataset_id: str, column: str, n: int = 10, ascending: bool = False):
    try:
        return top_n_analysis(_load(dataset_id), column, n, ascending)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/filter")
def analyze_filter(dataset_id: str, column: str, operator: str, value: str):
    try:
        return filter_analysis(_load(dataset_id), column, operator, value)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/eda")
def analyze_full_eda(dataset_id: str):
    try:
        return full_eda_summary(_load(dataset_id))
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
