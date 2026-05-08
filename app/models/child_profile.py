from pydantic import BaseModel, Field


class ChildProfile(BaseModel):
    age: int = Field(ge=3, le=17)
    age_group: str = Field(min_length=3)
    language: str = Field(min_length=2)
