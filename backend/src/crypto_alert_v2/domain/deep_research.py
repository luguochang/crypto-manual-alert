from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_alert_v2.domain.models import ModelExecutionAudit
from crypto_alert_v2.providers.search import WebEvidence


MAX_RESEARCH_SOURCES = 8
MAX_RESEARCH_QUERIES = 3
ResearchHarnessMode = Literal["deepagents", "langchain"]
DeepResearchArtifactStatus = Literal["draft", "committed"]
DeepResearchCoverageStatus = Literal["complete", "partial"]
DeepResearchSearchProvider = Literal[
    "builtin_web_search",
    "tavily",
    "ddgs_metasearch",
    "deep_research_search",
    "search",
]
DeepResearchSearchErrorKind = Literal[
    "timeout",
    "server_error",
    "rate_limited",
    "connection_error",
    "unverified_server_tool_call",
    "missing_provider_citation",
    "missing_verified_evidence",
    "invalid_provider_response",
    "provider_error",
]
SourceIndex = Annotated[int, Field(ge=1, le=MAX_RESEARCH_SOURCES)]


class CitedResearchFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim: str = Field(min_length=1, max_length=2000)
    source_indexes: list[SourceIndex] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def require_unique_source_indexes(self) -> Self:
        if len(self.source_indexes) != len(set(self.source_indexes)):
            raise ValueError("source_indexes must be unique within each finding")
        return self


class ResearchSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    findings: list[CitedResearchFinding] = Field(min_length=1, max_length=12)


class DeepResearchReport(BaseModel):
    """Model-owned report content with application-owned citation indexes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    executive_summary: str = Field(min_length=1, max_length=6000)
    sections: list[ResearchSection] = Field(min_length=1, max_length=8)
    risk_notes: list[str] = Field(default_factory=list, max_length=12)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=12)

    def referenced_source_indexes(self) -> frozenset[int]:
        return frozenset(
            source_index
            for section in self.sections
            for finding in section.findings
            for source_index in finding.source_indexes
        )


class IndexedResearchSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    index: SourceIndex
    evidence: WebEvidence


class DeepResearchSearchFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_index: int = Field(ge=1, le=MAX_RESEARCH_QUERIES)
    provider: DeepResearchSearchProvider
    error_kind: DeepResearchSearchErrorKind
    retryable: bool
    attempt: int | None = Field(default=None, ge=1, le=3)


class DeepResearchSearchCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: DeepResearchCoverageStatus
    attempted_queries: int = Field(ge=1, le=MAX_RESEARCH_QUERIES)
    successful_queries: int = Field(ge=1, le=MAX_RESEARCH_QUERIES)
    failed_queries: list[DeepResearchSearchFailure] = Field(
        default_factory=list,
        max_length=MAX_RESEARCH_QUERIES - 1,
    )

    @model_validator(mode="after")
    def require_coherent_query_coverage(self) -> Self:
        failed_indexes = [item.query_index for item in self.failed_queries]
        if failed_indexes != sorted(set(failed_indexes)):
            raise ValueError("failed search query indexes must be unique and ordered")
        if any(index > self.attempted_queries for index in failed_indexes):
            raise ValueError("failed search query index exceeds attempted query count")
        if self.successful_queries + len(failed_indexes) != self.attempted_queries:
            raise ValueError(
                "search query coverage must account for every attempted query"
            )
        expected_status = "complete" if not failed_indexes else "partial"
        if self.status != expected_status:
            raise ValueError("search coverage status does not match failed queries")
        return self


class DeepResearchArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_type: Literal["deep_research_report"] = "deep_research_report"
    schema_version: Literal["1.0"] = "1.0"
    status: DeepResearchArtifactStatus = "draft"
    harness_mode: ResearchHarnessMode
    search_coverage: DeepResearchSearchCoverage
    report: DeepResearchReport
    sources: list[IndexedResearchSource] = Field(
        min_length=1,
        max_length=MAX_RESEARCH_SOURCES,
    )
    model_audits: list[ModelExecutionAudit] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_coherent_source_catalog(self) -> Self:
        indexes = [source.index for source in self.sources]
        if indexes != list(range(1, len(self.sources) + 1)):
            raise ValueError("research source indexes must be contiguous and ordered")
        evidence_keys = [
            (str(source.evidence.final_url), source.evidence.content_hash)
            for source in self.sources
        ]
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError(
                "research source catalog cannot contain duplicate evidence"
            )
        unknown = self.report.referenced_source_indexes() - set(indexes)
        if unknown:
            raise ValueError(
                "research report references an unknown evidence source index: "
                + ", ".join(str(index) for index in sorted(unknown))
            )
        return self


def materialize_deep_research_artifact(
    *,
    report: DeepResearchReport,
    evidence: tuple[WebEvidence, ...],
    harness_mode: ResearchHarnessMode,
    search_coverage: DeepResearchSearchCoverage,
    model_audits: tuple[ModelExecutionAudit, ...],
    status: DeepResearchArtifactStatus = "draft",
) -> DeepResearchArtifact:
    if not evidence:
        raise ValueError("deep research requires at least one verified source")
    if len(evidence) > MAX_RESEARCH_SOURCES:
        raise ValueError(
            f"deep research cannot persist more than {MAX_RESEARCH_SOURCES} sources"
        )
    return DeepResearchArtifact(
        status=status,
        harness_mode=harness_mode,
        search_coverage=search_coverage,
        report=report,
        sources=[
            IndexedResearchSource(index=index, evidence=item)
            for index, item in enumerate(evidence, start=1)
        ],
        model_audits=list(model_audits),
    )


def commit_deep_research_artifact(
    artifact: DeepResearchArtifact,
) -> DeepResearchArtifact:
    if artifact.status != "draft":
        raise ValueError("only a draft deep research artifact can be committed")
    return DeepResearchArtifact.model_validate(
        {
            **artifact.model_dump(mode="json"),
            "status": "committed",
        }
    )


__all__ = [
    "CitedResearchFinding",
    "DeepResearchArtifact",
    "DeepResearchArtifactStatus",
    "DeepResearchCoverageStatus",
    "DeepResearchReport",
    "DeepResearchSearchCoverage",
    "DeepResearchSearchErrorKind",
    "DeepResearchSearchFailure",
    "DeepResearchSearchProvider",
    "IndexedResearchSource",
    "MAX_RESEARCH_SOURCES",
    "MAX_RESEARCH_QUERIES",
    "ResearchHarnessMode",
    "ResearchSection",
    "commit_deep_research_artifact",
    "materialize_deep_research_artifact",
]
