from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.dataset_manager import DatasetNotFoundError
from app.services import semantic_layer


router = APIRouter(prefix="/api/business-context", tags=["Business Context"])


class MetricRequest(BaseModel):
    name: str
    column: str
    aggregation: str = "sum"
    description: str = ""


class SynonymRequest(BaseModel):
    alias: str
    canonical: str


class RuleRequest(BaseModel):
    rule: str


class NotesRequest(BaseModel):
    notes: str


@router.get("/{dataset_id}")
def get_context(dataset_id: str):
    try:
        return semantic_layer.get_context(dataset_id)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{dataset_id}/metrics")
def add_metric(dataset_id: str, request: MetricRequest):
    try:
        return semantic_layer.upsert_metric(
            dataset_id, request.name, request.column, request.aggregation, request.description
        )
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.delete("/{dataset_id}/metrics/{name}")
def remove_metric(dataset_id: str, name: str):
    try:
        return semantic_layer.delete_metric(dataset_id, name)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{dataset_id}/synonyms")
def add_synonym(dataset_id: str, request: SynonymRequest):
    try:
        return semantic_layer.upsert_synonym(dataset_id, request.alias, request.canonical)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.delete("/{dataset_id}/synonyms/{alias}")
def remove_synonym(dataset_id: str, alias: str):
    try:
        return semantic_layer.delete_synonym(dataset_id, alias)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{dataset_id}/rules")
def add_rule(dataset_id: str, request: RuleRequest):
    try:
        return semantic_layer.add_rule(dataset_id, request.rule)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.delete("/{dataset_id}/rules/{index}")
def remove_rule(dataset_id: str, index: int):
    try:
        return semantic_layer.delete_rule(dataset_id, index)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.put("/{dataset_id}/notes")
def update_notes(dataset_id: str, request: NotesRequest):
    try:
        return semantic_layer.set_notes(dataset_id, request.notes)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
