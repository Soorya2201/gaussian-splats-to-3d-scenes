"""Pydantic request/response models. Mirrors frontend/src/types/scene.ts."""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

Vec3 = Tuple[float, float, float]

RelationType = Literal[
    "on_floor",
    "on_top_of",
    "against_wall",
    "left_of",
    "right_of",
    "in_front_of",
    "behind",
    "near",
    "center_of_room",
]

# ---------- /parse-command ----------


class ObjectRef(BaseModel):
    id: str
    label: str


class ParseRequest(BaseModel):
    text: str
    objects: List[ObjectRef] = Field(default_factory=list)
    hasRoom: bool = False


class Command(BaseModel):
    """One structured command. Only fields relevant to `action` are populated."""

    action: Literal["place", "add", "remove", "scale", "clear", "error"]
    object: Optional[str] = None
    relation: Optional[RelationType] = None
    target: Optional[str] = None
    align: Optional[Literal["center", "left", "right"]] = None
    targetHeight: Optional[float] = None
    factor: Optional[float] = None
    message: Optional[str] = None


# ---------- /validate-placement ----------


class ValidateRequest(BaseModel):
    image_base64: str
    object: str
    relation_phrase: str
    target: str


class ValidateResponse(BaseModel):
    pass_: bool = Field(alias="pass")
    reason: str
    suggestion: Literal[
        "move_up", "move_down", "move_left", "move_right", "scale_up", "scale_down", "none"
    ]

    model_config = {"populate_by_name": True}


# ---------- scene persistence ----------


class BBox(BaseModel):
    min: Vec3
    max: Vec3
    size: Vec3


class ObjectTransform(BaseModel):
    position: Vec3
    rotationY: float
    scale: float


class ObjectRelation(BaseModel):
    type: RelationType
    target: str
    align: Optional[Literal["center", "left", "right"]] = None
    offset: Optional[float] = None


class SceneObjectModel(BaseModel):
    id: str
    label: str
    assetUrl: str
    transform: ObjectTransform
    rawSize: Vec3
    targetHeight: float
    relation: Optional[ObjectRelation] = None
    worldBBox: Optional[BBox] = None
    verified: Literal["pending", "pass", "flagged"]
    validationNote: Optional[str] = None


class RoomSceneModel(BaseModel):
    id: str
    assetUrl: str
    kind: Literal["glb", "splat"]
    floorY: float
    bounds: BBox


class SceneGraphModel(BaseModel):
    room: Optional[RoomSceneModel] = None
    objects: List[SceneObjectModel] = Field(default_factory=list)
    version: int = 0


class SaveRequest(BaseModel):
    name: str
    graph: SceneGraphModel
