import type { components } from "@/lib/api/generated/schema";

type Schemas = components["schemas"];

export type RunStatus = Schemas["RunStatus"];
export type Severity = Schemas["Severity"];
export type Confidence = Schemas["Confidence"];
export type FindingType = Schemas["FindingType"];
export type TriageStatus = Schemas["TriageStatus"];
export type TriageResponse = Schemas["TriageResponse"];
export type BulkTriageResponse = Schemas["BulkTriageResponse"];

export type FindingResponse = Schemas["FindingResponse"];
export type FindingsResponse = Schemas["FindingsResponse"];
export type RunStatusResponse = Schemas["RunStatusResponse"];
export type RunListItem = Schemas["RunListItem"];
export type RunListResponse = Schemas["RunListResponse"];
export type NotificationResponse = Schemas["NotificationResponse"];
export type NotificationListResponse = Schemas["NotificationListResponse"];
export type ScopeResponse = Schemas["ScopeResponse"];
export type UserResponse = Schemas["UserResponse"];
export type UserListResponse = Schemas["UserListResponse"];
export type InvitationListResponse = Schemas["InvitationListResponse"];
export type SearchResponse = Schemas["SearchResponse"];
export type GlobalSearchResponse = Schemas["GlobalSearchResponse"];
export type FindingSearchHit = Schemas["FindingSearchHit"];
export type MetadataSearchHit = Schemas["MetadataSearchHit"];
export type ScopeListResponse = Schemas["ScopeListResponse"];

export type SeverityKey = Severity | "unclassified";

export function severityKey(severity: Severity | null | undefined): SeverityKey {
  return severity ?? "unclassified";
}

export type RunComparisonResponse = Schemas["RunComparisonResponse"];
export type ComparedFindingResponse = Schemas["ComparedFindingResponse"];
export type InvestigationStatus = Schemas["InvestigationStatus"];
export type InvestigationResponse = Schemas["InvestigationResponse"];
export type InvestigationListResponse = Schemas["InvestigationListResponse"];
export type InvestigationRunResponse = Schemas["InvestigationRunResponse"];
export type GraphNodeKind = Schemas["GraphNodeKind"];
export type GraphNodeResponse = Schemas["GraphNodeResponse"];
export type GraphEdgeResponse = Schemas["GraphEdgeResponse"];
export type GraphLayerResponse = Schemas["GraphLayerResponse"];
export type GraphMetricsResponse = Schemas["GraphMetricsResponse"];
export type RunGraphResponse = Schemas["RunGraphResponse"];
