"""Minimal SCIM 2.0 schemas (RFC 7643/7644).

Only the fields Portfolio-Pulse actually persists or returns. Extensions:
- `urn:portfolio-pulse:User:role` carries the role string (gp/analyst/lp).
- `urn:portfolio-pulse:User:sector` carries the analyst sector scoping.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
PORTFOLIO_USER_EXT = "urn:portfolio-pulse:User"


class Name(BaseModel):
    given_name: str | None = Field(default=None, alias="givenName")
    family_name: str | None = Field(default=None, alias="familyName")

    model_config = ConfigDict(populate_by_name=True)


class Email(BaseModel):
    value: str
    primary: bool = True


class GroupRef(BaseModel):
    value: str
    display: str | None = None


class Meta(BaseModel):
    resource_type: str = Field(alias="resourceType")
    created: str | None = None
    last_modified: str | None = Field(default=None, alias="lastModified")
    location: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class ScimUser(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [USER_SCHEMA])
    id: str | None = None
    external_id: str | None = Field(default=None, alias="externalId")
    user_name: str = Field(alias="userName")
    name: Name | None = None
    emails: list[Email] = Field(default_factory=list)
    active: bool = True
    groups: list[GroupRef] = Field(default_factory=list)
    meta: Meta | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class GroupMember(BaseModel):
    value: str
    display: str | None = None


class ScimGroup(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [GROUP_SCHEMA])
    id: str | None = None
    external_id: str | None = Field(default=None, alias="externalId")
    display_name: str = Field(alias="displayName")
    members: list[GroupMember] = Field(default_factory=list)
    meta: Meta | None = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [LIST_SCHEMA])
    total_results: int = Field(alias="totalResults")
    resources: list[dict[str, Any]] = Field(default_factory=list, alias="Resources")
    start_index: int = Field(default=1, alias="startIndex")
    items_per_page: int = Field(default=0, alias="itemsPerPage")

    model_config = ConfigDict(populate_by_name=True)


class ScimError(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [ERROR_SCHEMA])
    status: str
    detail: str

    model_config = ConfigDict(populate_by_name=True)
