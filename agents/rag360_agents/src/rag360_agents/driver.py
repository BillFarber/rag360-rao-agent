import json

import time
from typing import Iterable, Optional, TypedDict

from httpx import AsyncClient, BasicAuth, DigestAuth
from rao_agent.driver import Driver

from nuclia_agents.drivers.marklogic.config import MarkLogicDriverConfig
from rao_agent import logger

from rao_agent.utils.http import safe_http_client


class LabelDef(TypedDict, total=False):
    label: str
    description: str
    requireWhen: list[str]
    avoidWhen: list[str]


class FilterDef(TypedDict, total=False):
    filterType: str
    dataType: str
    description: str
    operators: list[str]
    exampleValues: list[str]


class DefinitionResponse(TypedDict, total=False):
    labels: list[LabelDef]
    filters: dict[str, FilterDef]


class RetrieveFilter(TypedDict):
    """A single filter constraint for the retrieve API."""

    constraintType: str
    constraintOperator: str
    constraintValue: str


class MarkLogicConnection:
    def __init__(
        self,
        base_url: str,
        auth_method: str = "api_key",
        auth_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        jwt_token: Optional[str] = None,
    ):
        self._client = AsyncClient()
        self._client.base_url = base_url

        if auth_method == "digest":
            assert username is not None and password is not None
            self._client.auth = DigestAuth(username, password)
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        elif auth_method == "basic":
            assert username is not None and password is not None
            self._client.auth = BasicAuth(username, password)
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        elif auth_method == "jwt":
            assert jwt_token is not None
            self._client.headers = {"Authorization": f"Bearer {jwt_token}"}
            self._auth_expires = float("inf")
            self._auth_url = None
            self._api_key = None
        else:
            self._auth_expires = 0
            self._auth_url = auth_url
            self._api_key = api_key

    def _build_retrieve_params(
        self,
        query: str,
        top_k: int,
        must_not_have_labels: Optional[Iterable[str]] = None,
        must_have_labels: Optional[Iterable[str]] = None,
        filters: Optional[dict[str, "RetrieveFilter"]] = None,
    ) -> dict:
        """Build parameters for the MarkLogic retrieve API call.

        Args:
            query: Search query text
            top_k: Maximum number of results to return
            must_not_have_labels: Labels that documents must NOT have
            must_have_labels: Labels that documents must have
            filters: Field-value filters (e.g. document_topic constraint)

        Returns:
            Dictionary of parameters for the retrieve API call
        """
        must_not = set(must_not_have_labels or [])
        must_have = set(must_have_labels or [])

        # Conflict resolution: exclude wins
        conflicts = must_not & must_have
        if conflicts:
            must_have -= conflicts
            logger.warning(
                "Labels present in both must-have and must-not-have: %s",
                sorted(conflicts),
            )

        params: dict = {"text": query, "topk": top_k}

        if must_not or must_have:
            labels: dict[str, dict[str, str]] = {}
            for l in sorted(must_have):
                labels[l] = {"constraintValue": "MustHave"}
            for l in sorted(must_not):
                # MustNotHave wins if same label appears in both (because we apply it last)
                labels[l] = {"constraintValue": "MustNotHave"}
            params["labels"] = labels

        if filters:
            params["filters"] = filters

        return params

    async def retrieve(
        self,
        query: str,
        *,
        must_not_have_labels: Optional[Iterable[str]] = None,
        must_have_labels: Optional[Iterable[str]] = None,
        filters: Optional[dict[str, "RetrieveFilter"]] = None,
        top_k: int = 20,
    ) -> list[str]:
        await self._ensure_auth()

        params = self._build_retrieve_params(
            query=query,
            top_k=top_k,
            must_not_have_labels=must_not_have_labels,
            must_have_labels=must_have_labels,
            filters=filters,
        )

        logger.debug("Querying MarkLogic with params: %s", params)
        response = await self._client.post("/v1/retrieve", json=params)
        response.raise_for_status()
        return [
            m["id"] for m in response.json().get("matches", []) if "id" in m
        ]

    async def definition(self) -> DefinitionResponse:
        await self._ensure_auth()
        response = await self._client.get("/v1/retrieve/definition")
        response.raise_for_status()
        data = response.json()
        return DefinitionResponse(
            labels=data.get("labels", []),
            filters=data.get("filters", {}),
        )

    async def augment(self, ids: list[str]) -> list[str]:
        await self._ensure_auth()
        response = await self._client.get(
            "/v1/augment", params={"URIs": json.dumps(ids)}
        )
        response.raise_for_status()
        docs = []
        for doc in response.json()["documents"]:
            content = doc["document"]
            if isinstance(content, dict):
                docs.append(json.dumps(content))
            else:
                docs.append(content)
        return docs

    async def _ensure_auth(self):
        if self._auth_expires > time.monotonic():
            return

        async with safe_http_client() as session:
            response = await session.post(
                self._auth_url,
                data={"grant_type": "apikey", "key": self._api_key},
            )
            response.raise_for_status()
            doc = response.json()
            token = doc["access_token"]
            expiry_minutes = doc["expires_in"]
            self._client.headers = {"Authorization": f"Bearer {token}"}
            self._auth_expires = time.monotonic() + (60 * expiry_minutes * 0.9)


# @driver(
#     id="marklogic",
#     title="MarkLogic Driver",
#     description="Driver for interacting with the MarkLogic  API.",
#     config_schema=MarkLogicDriverConfig,
# )
class MarkLogicDriver(Driver):
    client: MarkLogicConnection

    @classmethod
    async def init(cls, driver: MarkLogicDriverConfig):
        client = MarkLogicConnection(
            base_url=driver.config.base_url,
            auth_method=driver.config.auth_method,
            auth_url=driver.config.auth_url,
            api_key=driver.config.api_key,
            username=driver.config.username,
            password=driver.config.password,
            jwt_token=driver.config.jwt_token,
            transport_verify=driver.config.transport_verify,
        )
        return cls(
            client=client,
            name=driver.name,
            provider=driver.provider,
        )
