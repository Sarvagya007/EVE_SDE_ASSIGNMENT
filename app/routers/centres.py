from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/centres", tags=["Centres & Tests"])


@router.get("/")
def list_centres(db: Session = Depends(get_db)):
    centres = db.query(models.DiagnosticCentre).all()
    results = []
    for centre in centres:
        tests = db.query(models.CentreTestMapping).filter_by(centre_id=centre.id).all()
        results.append({
            "id": centre.id,
            "name": centre.name,
            "location": centre.location,
            "available_tests": [
                {
                    "test_id": item.test_id,
                    "test_name": item.test.name if item.test else "",
                    "price": item.price,
                }
                for item in tests
            ],
        })
    return results


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_centre(payload: schemas.CentreCreate, db: Session = Depends(get_db)):
    centre = models.DiagnosticCentre(name=payload.name, location=payload.location)
    db.add(centre)
    db.commit()
    db.refresh(centre)
    return {"id": centre.id, "name": centre.name, "location": centre.location}


@router.post("/{centre_id}/tests", status_code=status.HTTP_201_CREATED)
def add_test_to_centre(
    centre_id: int,
    payload: schemas.CentreTestMappingCreate,
    db: Session = Depends(get_db),
):
    centre = db.query(models.DiagnosticCentre).filter_by(id=centre_id).first()
    if not centre:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic centre not found.",
        )

    # Resolve or create test
    test = None
    if payload.test_id:
        test = db.query(models.DiagnosticTest).filter_by(id=payload.test_id).first()
    elif payload.test_name:
        test = db.query(models.DiagnosticTest).filter_by(name=payload.test_name).first()
        if not test:
            test = models.DiagnosticTest(name=payload.test_name)
            db.add(test)
            db.commit()
            db.refresh(test)

    if not test:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Valid test_id or test_name must be provided.",
        )

    # Check for duplicate
    existing = db.query(models.CentreTestMapping).filter_by(
        centre_id=centre.id, test_id=test.id
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Test already exists at this centre.",
        )

    mapping = models.CentreTestMapping(
        centre_id=centre.id,
        test_id=test.id,
        price=payload.price,
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return {
        "id": mapping.id,
        "centre_id": mapping.centre_id,
        "test_id": mapping.test_id,
        "test_name": test.name,
        "price": mapping.price,
    }
