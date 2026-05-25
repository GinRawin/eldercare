import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.models.elder_profile import ElderProfile
from app.schemas.elder_profile import ElderProfileCreate, ElderProfileOut, ElderProfileUpdate

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _serialize(profile: ElderProfile) -> ElderProfileOut:
    data = {
        "elder_id": profile.elder_id,
        "name": profile.name,
        "age": profile.age,
        "gender": profile.gender,
        "allergies": json.loads(profile.allergies) if profile.allergies else [],
        "diseases": json.loads(profile.diseases) if profile.diseases else [],
        "health_notes": profile.health_notes,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    return ElderProfileOut(**data)


@router.get("/{elder_id}", response_model=ElderProfileOut, summary="查询老人档案")
def get_profile(elder_id: str, db: Session = Depends(get_db)):
    profile = db.get(ElderProfile, elder_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Elder not found")
    return _serialize(profile)


@router.post("", response_model=ElderProfileOut, status_code=201, summary="创建老人档案")
def create_profile(body: ElderProfileCreate, db: Session = Depends(get_db)):
    if db.get(ElderProfile, body.elder_id):
        raise HTTPException(status_code=409, detail="Elder ID already exists")
    profile = ElderProfile(
        elder_id=body.elder_id,
        name=body.name,
        age=body.age,
        gender=body.gender,
        allergies=json.dumps(body.allergies, ensure_ascii=False),
        diseases=json.dumps(body.diseases, ensure_ascii=False),
        health_notes=body.health_notes,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _serialize(profile)


@router.patch("/{elder_id}", response_model=ElderProfileOut, summary="更新老人档案")
def update_profile(elder_id: str, body: ElderProfileUpdate, db: Session = Depends(get_db)):
    profile = db.get(ElderProfile, elder_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Elder not found")
    if body.name is not None:
        profile.name = body.name
    if body.age is not None:
        profile.age = body.age
    if body.gender is not None:
        profile.gender = body.gender
    if body.allergies is not None:
        profile.allergies = json.dumps(body.allergies, ensure_ascii=False)
    if body.diseases is not None:
        profile.diseases = json.dumps(body.diseases, ensure_ascii=False)
    if body.health_notes is not None:
        profile.health_notes = body.health_notes
    db.commit()
    db.refresh(profile)
    return _serialize(profile)
