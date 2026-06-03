"""Pydantic v2 models for the Luminous3D desired-state infrastructure model.

Layering (see mappings/ and policies/ for the rest of the enforcement story):

* JSON Schema (schemas/infra.schema.json) is the *canonical* per-document
  validator: envelope shape, closedness, enums, ranges, discriminator.
* These Pydantic models are the *programmatic* validator. They mirror the JSON
  Schema 1:1 for single-document validation and additionally implement the
  cross-object / graph constraints that JSON Schema cannot practically express
  (referential integrity, unique composite keys, IP-in-prefix, public-exposure
  approval). Those live in `check_manifest()` at the bottom of this module.
* OPA/Conftest (policies/) re-implement the security guardrails so they also
  run against *generated* artifacts, not just the abstract model.

Run `python infra_models.py --emit-schema` to export a (Pydantic-flavored)
JSON Schema, and `python infra_models.py --check <file...>` to validate +
run the graph checks.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from typing import Annotated, Literal, Optional, Union

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

API_VERSION = "infra.luminous3d.example/v1alpha1"

# ---------------------------------------------------------------------------
# Primitive constrained types
# ---------------------------------------------------------------------------
Slug = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$",
                           min_length=1, max_length=63)
]
ApiVersion = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?/v[0-9]+((alpha|beta)[0-9]+)?$")
]
Mac = Annotated[str, StringConstraints(pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")]
Duration = Annotated[str, StringConstraints(pattern=r"^[0-9]+(ms|s|m|h|d)$")]
Port = Annotated[int, Field(ge=1, le=65535)]
VlanId = Annotated[int, Field(ge=1, le=4094)]
VmId = Annotated[int, Field(ge=100, le=999_999_999)]

L4Protocol = Literal["tcp", "udp", "sctp", "icmp", "any"]
Criticality = Literal["low", "medium", "high", "critical"]
TrustLevel = Literal["management", "trusted", "user", "guest", "iot", "dmz", "untrusted"]
SecretProvider = Literal["openbao", "vault", "sops", "onepassword", "env", "file"]


class Strict(BaseModel):
    """Closed base model: forbids unknown keys, allows alias population by name."""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ---------------------------------------------------------------------------
# Reusable value objects
# ---------------------------------------------------------------------------
KINDS = (
    "Site", "NetworkZone", "Vlan", "Prefix", "Gateway", "Device", "Interface",
    "ProxmoxCluster", "Host", "VirtualMachine", "LxcContainer", "Service",
    "ServiceDependency", "FirewallPolicy", "AllowedFlow", "BackupClass",
    "SecretRef", "MonitoringCheck", "FailureScenario",
)
Kind = Literal[KINDS]  # type: ignore[valid-type]


class ObjectRef(Strict):
    """Reference to another object by composite key (kind + name [+ namespace])."""
    kind: Kind
    name: Slug
    namespace: Optional[Slug] = None


class SecretRefInline(Strict):
    """Inline pointer to a secret. NEVER carries the value."""
    ref: Optional[Slug] = None
    provider: Optional[SecretProvider] = None
    path: Optional[str] = None
    key: Optional[str] = None

    @model_validator(mode="after")
    def _ref_xor_inline(self) -> "SecretRefInline":
        if self.ref is None and not (self.provider and self.path):
            raise ValueError("SecretRef must set either 'ref' or both 'provider' and 'path'")
        return self


# Mirror of the Cidr $def regexes in _build/build_schema.py. Kept in sync by
# the drift gate (examples/invalid/structural/cidr-prefixless.yaml): if these
# diverge from the schema, C2 fails. A bare address (no /prefix) or an
# IPv4-mapped IPv6 form is rejected here exactly as the JSON Schema rejects it.
_CIDR_RE = (
    re.compile(r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)/(3[0-2]|[12]?\d)$"),
    re.compile(r"^([0-9a-fA-F:]+)/(12[0-8]|1[01]\d|[1-9]?\d)$"),
)


def _validate_cidr(v: str) -> str:
    if not any(rx.match(v) for rx in _CIDR_RE):
        raise ValueError(f"not a valid CIDR (needs an explicit prefix length): {v!r}")
    ipaddress.ip_network(v, strict=False)  # semantic sanity on top of shape
    return v


def _validate_ip(v: str) -> str:
    ipaddress.ip_address(v)
    return v


Cidr = Annotated[str, Field()]
IpAddress = Annotated[str, Field()]


class IpConfig(Strict):
    address: Optional[str] = None  # "dhcp" or CIDR
    gateway: Optional[str] = None

    @field_validator("address")
    @classmethod
    def _addr(cls, v):
        if v is None or v == "dhcp":
            return v
        return _validate_cidr(v)

    @field_validator("gateway")
    @classmethod
    def _gw(cls, v):
        return None if v is None else _validate_ip(v)


class GuestNic(Strict):
    name: str
    bridge: str
    model: Literal["virtio", "e1000", "rtl8139", "vmxnet3"] = "virtio"
    mac: Optional[Mac] = None
    mtu: Optional[Annotated[int, Field(ge=576, le=9000)]] = None
    vlan: Optional[Union[VlanId, ObjectRef]] = None
    ipv4: Optional[IpConfig] = None
    ipv6: Optional[IpConfig] = None
    firewall: bool = True


class DiskSpec(Strict):
    id: str
    datastore: str
    sizeGb: Annotated[int, Field(ge=1)]
    interface: Optional[Literal["scsi", "virtio", "sata", "ide"]] = None
    iothread: Optional[bool] = None
    discard: Optional[bool] = None
    ssd: Optional[bool] = None


class MountPoint(Strict):
    path: str
    volume: Optional[str] = None
    sizeGb: Optional[Annotated[int, Field(ge=1)]] = None
    backup: bool = False
    readOnly: bool = False
    bind: bool = False


class PortSpec(Strict):
    protocol: L4Protocol
    port: Port
    name: Optional[str] = None


class ExposureDecision(Strict):
    level: Literal["internal", "lan", "vpn", "public"]
    approved: bool = False
    approvedBy: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _public_needs_approval(self) -> "ExposureDecision":
        # Cross-field rule JSON Schema would need if/then for; also enforced in OPA.
        if self.level == "public" and not self.approved:
            raise ValueError("exposure.level=public requires approved=true with approvedBy/reason")
        return self


class FlowEndpoint(Strict):
    zone: Optional[ObjectRef] = None
    prefix: Optional[ObjectRef] = None
    cidr: Optional[str] = None
    service: Optional[ObjectRef] = None
    any: Optional[bool] = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "FlowEndpoint":
        if not any([self.zone, self.prefix, self.cidr, self.service, self.any]):
            raise ValueError("flow endpoint requires at least one selector")
        return self


# ---------------------------------------------------------------------------
# Per-kind specs
# ---------------------------------------------------------------------------
class SiteLocation(Strict):
    facility: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None


class SiteSpec(Strict):
    role: Literal["home", "offsite", "cloud", "edge"]
    displayName: Optional[str] = None
    location: Optional[SiteLocation] = None
    notes: Optional[str] = None


class NetworkZoneSpec(Strict):
    site: ObjectRef
    trustLevel: TrustLevel
    defaultDeny: bool = True
    description: Optional[str] = None


class VlanSpec(Strict):
    site: ObjectRef
    vlanId: VlanId
    vlanName: str
    zone: Optional[ObjectRef] = None
    description: Optional[str] = None


class DhcpRange(Strict):
    start: str
    end: str


class DhcpSpec(Strict):
    enabled: bool = False
    ranges: Optional[list[DhcpRange]] = None


class PrefixSpec(Strict):
    cidr: str
    site: Optional[ObjectRef] = None
    vlan: Optional[ObjectRef] = None
    role: Optional[Literal["management", "server", "user", "guest", "iot", "dmz",
                           "loopback", "transit", "container", "storage"]] = None
    gateway: Optional[str] = None
    dhcp: Optional[DhcpSpec] = None
    description: Optional[str] = None

    @field_validator("cidr")
    @classmethod
    def _cidr(cls, v):
        return _validate_cidr(v)


class Vrrp(Strict):
    group: Optional[Annotated[int, Field(ge=1, le=255)]] = None
    priority: Optional[Annotated[int, Field(ge=1, le=254)]] = None
    virtualAddress: Optional[str] = None


class GatewaySpec(Strict):
    prefix: ObjectRef
    address: str
    device: Optional[ObjectRef] = None
    interface: Optional[ObjectRef] = None
    vrrp: Optional[Vrrp] = None
    description: Optional[str] = None


class DeviceSpec(Strict):
    site: ObjectRef
    role: Literal["router", "switch", "firewall", "ap", "server", "appliance",
                  "pdu", "storage", "other"]
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    platform: Optional[str] = None
    serialNumber: Optional[str] = None
    managementIp: Optional[str] = None


class InterfaceSpec(Strict):
    device: ObjectRef
    ifName: str
    type: Literal["physical", "lag", "vlan", "virtual", "mgmt", "loopback"]
    enabled: bool = True
    mac: Optional[Mac] = None
    mtu: Optional[Annotated[int, Field(ge=576, le=9216)]] = None
    mode: Optional[Literal["access", "tagged", "tagged-all", "routed"]] = None
    untaggedVlan: Optional[ObjectRef] = None
    taggedVlans: Optional[list[ObjectRef]] = None
    addresses: Optional[list[str]] = None
    lagMembers: Optional[list[ObjectRef]] = None
    description: Optional[str] = None


class ProxmoxClusterSpec(Strict):
    site: ObjectRef
    nodes: Annotated[list[ObjectRef], Field(min_length=1)]
    quorumExpected: Optional[Annotated[int, Field(ge=1)]] = None
    apiEndpoint: Optional[str] = None
    tokenRef: Optional[SecretRefInline] = None
    description: Optional[str] = None


class HostStorage(Strict):
    id: str
    type: Optional[Literal["lvm", "lvmthin", "zfs", "dir", "nfs", "cephfs", "rbd"]] = None
    sizeGb: Optional[Annotated[int, Field(ge=1)]] = None


class HostSpec(Strict):
    site: ObjectRef
    role: Literal["hypervisor", "baremetal-service", "storage", "other"]
    cluster: Optional[ObjectRef] = None
    device: Optional[ObjectRef] = None
    proxmoxNode: Optional[str] = None
    cpuCores: Optional[Annotated[int, Field(ge=1)]] = None
    memoryMb: Optional[Annotated[int, Field(ge=256)]] = None
    managementIp: Optional[str] = None
    storage: Optional[list[HostStorage]] = None


class _GuestBase(Strict):
    host: Optional[ObjectRef] = None
    cluster: Optional[ObjectRef] = None
    proxmoxNode: Optional[str] = None
    vmId: Optional[VmId] = None
    cores: Annotated[int, Field(ge=1)]
    memoryMb: Annotated[int, Field(ge=16)]
    networkInterfaces: Optional[list[GuestNic]] = None
    startOnBoot: bool = True
    tags: Optional[list[str]] = None
    description: Optional[str] = None


class CloudInit(Strict):
    username: Optional[str] = None
    sshKeysRef: Optional[SecretRefInline] = None
    passwordRef: Optional[SecretRefInline] = None
    userDataFileId: Optional[str] = None
    datastore: Optional[str] = None


class VirtualMachineSpec(_GuestBase):
    template: Optional[str] = None
    osType: Optional[str] = None
    disks: Optional[list[DiskSpec]] = None
    agent: bool = True
    cloudInit: Optional[CloudInit] = None


class LxcFeatures(Strict):
    nesting: bool = False
    fuse: bool = False
    keyctl: bool = False


class LxcContainerSpec(_GuestBase):
    ostemplate: str
    osType: Optional[str] = None
    unprivileged: bool = True
    features: Optional[LxcFeatures] = None
    swapMb: Optional[Annotated[int, Field(ge=0)]] = None
    rootfs: Optional[DiskSpec] = None
    mounts: Optional[list[MountPoint]] = None
    cpuUnits: Optional[Annotated[int, Field(ge=0)]] = None
    sshKeysRef: Optional[SecretRefInline] = None
    passwordRef: Optional[SecretRefInline] = None


class ServiceImplementation(Strict):
    type: Literal["docker-compose", "native", "systemd", "helm"]
    composeServiceName: Optional[str] = None
    composeFile: Optional[str] = None
    image: Optional[str] = None
    unitName: Optional[str] = None


class ServiceSpec(Strict):
    runsOn: ObjectRef
    exposure: ExposureDecision
    serviceType: Optional[Literal["web", "db", "dns", "dhcp", "monitoring", "storage",
                                  "automation", "proxy", "auth", "messaging", "other"]] = None
    criticality: Optional[Criticality] = None
    ports: Optional[list[PortSpec]] = None
    vip: Optional[str] = None
    fqdn: Optional[str] = None
    backupClass: Optional[ObjectRef] = None
    healthcheck: Optional[ObjectRef] = None
    secrets: Optional[list[SecretRefInline]] = None
    implementation: Optional[ServiceImplementation] = None


class ServiceDependencySpec(Strict):
    from_: ObjectRef = Field(alias="from")
    to: ObjectRef
    type: Literal["requires", "soft-requires", "uses"]
    protocol: Optional[L4Protocol] = None
    port: Optional[Port] = None
    description: Optional[str] = None


class FirewallPolicySpec(Strict):
    defaultAction: Literal["drop", "reject", "accept"]
    appliesTo: Literal["zone-pair", "device", "global"]
    device: Optional[ObjectRef] = None
    fromZone: Optional[ObjectRef] = None
    toZone: Optional[ObjectRef] = None
    description: Optional[str] = None


class AllowedFlowSpec(Strict):
    policy: ObjectRef
    source: FlowEndpoint
    destination: FlowEndpoint
    protocol: L4Protocol
    ports: Optional[list[Union[Port, str]]] = None
    action: Literal["allow"] = "allow"
    logging: bool = False
    description: Optional[str] = None


class Retention(Strict):
    daily: Optional[Annotated[int, Field(ge=0)]] = None
    weekly: Optional[Annotated[int, Field(ge=0)]] = None
    monthly: Optional[Annotated[int, Field(ge=0)]] = None
    yearly: Optional[Annotated[int, Field(ge=0)]] = None

    @model_validator(mode="after")
    def _nonempty(self) -> "Retention":
        if not any([self.daily, self.weekly, self.monthly, self.yearly]):
            raise ValueError("retention must set at least one period")
        return self


class BackupClassSpec(Strict):
    schedule: str
    target: str
    retention: Retention
    restoreTarget: Optional[str] = None
    rpoMinutes: Optional[Annotated[int, Field(ge=0)]] = None
    rtoMinutes: Optional[Annotated[int, Field(ge=0)]] = None
    encryptionSecretRef: Optional[SecretRefInline] = None
    description: Optional[str] = None


class SecretRotation(Strict):
    enabled: bool = False
    intervalDays: Optional[Annotated[int, Field(ge=1)]] = None


class SecretRefSpec(Strict):
    provider: SecretProvider
    path: str
    keys: Optional[list[str]] = None
    rotation: Optional[SecretRotation] = None
    description: Optional[str] = None


class MonitoringParameters(Strict):
    url: Optional[str] = None
    port: Optional[Port] = None
    expectStatus: Optional[int] = None
    expectString: Optional[str] = None
    query: Optional[str] = None
    scriptPath: Optional[str] = None


class MonitoringCheckSpec(Strict):
    target: ObjectRef
    type: Literal["http", "https", "tcp", "icmp", "dns", "script", "snmp"]
    interval: Duration
    timeout: Optional[Duration] = None
    severity: Optional[Criticality] = None
    parameters: Optional[MonitoringParameters] = None
    notify: Optional[list[str]] = None
    description: Optional[str] = None


class Fault(Strict):
    type: Literal["host-down", "device-down", "link-down", "service-down", "site-down", "wan-down"]
    targets: Annotated[list[ObjectRef], Field(min_length=1)]


class FailoverItem(Strict):
    service: ObjectRef
    to: ObjectRef
    automatic: bool = False


class ExpectedOutcome(Strict):
    unavailableServices: Optional[list[ObjectRef]] = None
    degradedServices: Optional[list[ObjectRef]] = None
    failover: Optional[list[FailoverItem]] = None
    maxOutageMinutes: Optional[Annotated[int, Field(ge=0)]] = None


class ScenarioValidation(Strict):
    tool: Literal["batfish", "containerlab", "manual"]
    notes: Optional[str] = None


class FailureScenarioSpec(Strict):
    fault: Fault
    expected: ExpectedOutcome
    description: Optional[str] = None
    validation: Optional[ScenarioValidation] = None


# ---------------------------------------------------------------------------
# Envelope + discriminated union
# ---------------------------------------------------------------------------
class Metadata(Strict):
    name: Slug
    namespace: Optional[Slug] = None
    uid: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    owner: Optional[str] = None
    labels: Optional[dict[str, str]] = None
    annotations: Optional[dict[str, str]] = None


class _Obj(Strict):
    apiVersion: ApiVersion
    metadata: Metadata


def _kind_object(kind_name: str, spec_model: type[BaseModel]) -> type[_Obj]:
    ns = {
        "__annotations__": {"kind": Literal[kind_name], "spec": spec_model},  # type: ignore
        "__module__": __name__,
    }
    return type(f"{kind_name}Object", (_Obj,), ns)


SiteObject = _kind_object("Site", SiteSpec)
NetworkZoneObject = _kind_object("NetworkZone", NetworkZoneSpec)
VlanObject = _kind_object("Vlan", VlanSpec)
PrefixObject = _kind_object("Prefix", PrefixSpec)
GatewayObject = _kind_object("Gateway", GatewaySpec)
DeviceObject = _kind_object("Device", DeviceSpec)
InterfaceObject = _kind_object("Interface", InterfaceSpec)
ProxmoxClusterObject = _kind_object("ProxmoxCluster", ProxmoxClusterSpec)
HostObject = _kind_object("Host", HostSpec)
VirtualMachineObject = _kind_object("VirtualMachine", VirtualMachineSpec)
LxcContainerObject = _kind_object("LxcContainer", LxcContainerSpec)
ServiceObject = _kind_object("Service", ServiceSpec)
ServiceDependencyObject = _kind_object("ServiceDependency", ServiceDependencySpec)
FirewallPolicyObject = _kind_object("FirewallPolicy", FirewallPolicySpec)
AllowedFlowObject = _kind_object("AllowedFlow", AllowedFlowSpec)
BackupClassObject = _kind_object("BackupClass", BackupClassSpec)
SecretRefObject = _kind_object("SecretRef", SecretRefSpec)
MonitoringCheckObject = _kind_object("MonitoringCheck", MonitoringCheckSpec)
FailureScenarioObject = _kind_object("FailureScenario", FailureScenarioSpec)

AnyObject = Annotated[
    Union[
        SiteObject, NetworkZoneObject, VlanObject, PrefixObject, GatewayObject,
        DeviceObject, InterfaceObject, ProxmoxClusterObject, HostObject,
        VirtualMachineObject, LxcContainerObject, ServiceObject,
        ServiceDependencyObject, FirewallPolicyObject, AllowedFlowObject,
        BackupClassObject, SecretRefObject, MonitoringCheckObject,
        FailureScenarioObject,
    ],
    Field(discriminator="kind"),
]


class ManifestSpec(Strict):
    items: Annotated[list[AnyObject], Field(min_length=1)]  # type: ignore[valid-type]


class InfraManifest(Strict):
    apiVersion: ApiVersion
    kind: Literal["InfraManifest"]
    metadata: Metadata
    spec: ManifestSpec


AnyDocument = Annotated[Union[AnyObject, InfraManifest], Field(discriminator="kind")]
DocumentAdapter: TypeAdapter = TypeAdapter(AnyDocument)


# ---------------------------------------------------------------------------
# Graph-level checks (the Pydantic/Python enforcement layer)
# ---------------------------------------------------------------------------
def _flatten(docs: list) -> list:
    """Flatten InfraManifest bundles into a single list of validated objects."""
    out = []
    for d in docs:
        if getattr(d, "kind", None) == "InfraManifest":
            out.extend(d.spec.items)
        else:
            out.append(d)
    return out


def _walk_refs(obj, refs: list):
    """Collect every ObjectRef anywhere inside a model (depth-first)."""
    if isinstance(obj, ObjectRef):
        refs.append(obj)
        return
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            _walk_refs(getattr(obj, name), refs)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk_refs(item, refs)


def check_manifest(docs: list) -> list[str]:
    """Cross-object constraints JSON Schema cannot express. Returns error strings."""
    errors: list[str] = []
    objects = _flatten(docs)

    # 1. Unique composite key (kind, namespace, name)
    index: dict[tuple, object] = {}
    for o in objects:
        ns = o.metadata.namespace or "default"
        key = (o.kind, ns, o.metadata.name)
        if key in index:
            errors.append(f"duplicate object {key}")
        index[key] = o

    # 2. Referential integrity (every ObjectRef must resolve)
    for o in objects:
        refs: list[ObjectRef] = []
        _walk_refs(o, refs)
        for r in refs:
            key = (r.kind, r.namespace or "default", r.name)
            if key not in index:
                errors.append(
                    f"{o.kind}/{o.metadata.name} references missing {r.kind}/{r.name}"
                )

    # 3. IP-in-prefix (guest NIC addresses must fall inside a declared Prefix)
    prefixes = [
        ipaddress.ip_network(o.spec.cidr, strict=False)
        for o in objects if o.kind == "Prefix"
    ]
    for o in objects:
        if o.kind not in ("VirtualMachine", "LxcContainer"):
            continue
        for nic in (o.spec.networkInterfaces or []):
            if nic.ipv4 and nic.ipv4.address and nic.ipv4.address != "dhcp":
                host = ipaddress.ip_interface(nic.ipv4.address).ip
                if prefixes and not any(host in p for p in prefixes):
                    errors.append(
                        f"{o.kind}/{o.metadata.name} NIC {nic.name} address "
                        f"{nic.ipv4.address} is not within any declared Prefix"
                    )
    return errors


def _load_file(path: str) -> tuple[list, bool, int]:
    """Parse a YAML file into (objects, closed_world, rc).

    ``closed_world`` is True when the file asserts a complete set whose internal
    references must all resolve -- i.e. it is an InfraManifest bundle or a
    multi-document stream. A file containing a single bare Object is an
    open-world *fragment* (it legitimately references siblings defined in other
    files), so only structural validation applies to it. ``rc`` is 1 on any
    structural failure.
    """
    objs: list = []
    rc = 0
    doc_count = 0
    saw_bundle = False
    for raw in yaml.safe_load_all(open(path).read()):
        if raw is None:
            continue
        doc_count += 1
        try:
            doc = DocumentAdapter.validate_python(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"SCHEMA FAIL {path}: {exc}")
            rc = 1
            continue
        if isinstance(doc, InfraManifest):
            saw_bundle = True
            objs.extend(doc.spec.items)
        else:
            objs.append(doc)
    closed_world = saw_bundle or doc_count > 1
    return objs, closed_world, rc


def load_and_check(paths: list[str], merge: bool = False) -> int:
    """Validate files structurally (always per-document) then run graph checks.

    By default each file is judged on its own: an InfraManifest bundle or a
    multi-document stream is a closed world whose references must all resolve;
    a single bare Object is an open-world fragment and gets structural checks
    only. Pass merge=True to pool every object across all files into one
    combined closed-world graph -- the correct mode for validating a real
    ``live/`` tree where the whole repository is the canonical desired state.
    """
    rc = 0
    if merge:
        pooled: list = []
        for path in paths:
            objs, _closed, frc = _load_file(path)
            rc = rc or frc
            pooled.extend(objs)
        if rc == 0:
            for e in check_manifest(pooled):
                print(f"GRAPH FAIL  {e}")
                rc = 1
    else:
        for path in paths:
            objs, closed_world, frc = _load_file(path)
            if frc:
                rc = 1
                continue
            if not closed_world:
                continue  # open-world fragment: structural validation only
            errs = check_manifest(objs)
            for e in errs:
                print(f"GRAPH FAIL  [{path}] {e}")
            if errs:
                rc = 1
    print("RESULT:", "PASS" if rc == 0 else "FAIL")
    return rc


def emit_schema() -> dict:
    return DocumentAdapter.json_schema(by_alias=True, ref_template="#/$defs/{model}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Desired-state model validator")
    parser.add_argument("--emit-schema", action="store_true", help="print Pydantic-derived JSON Schema")
    parser.add_argument("--check", nargs="+", metavar="FILE", help="validate files + graph checks")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="pool all --check files into one combined graph (whole-repo mode)",
    )
    args = parser.parse_args()
    if args.emit_schema:
        print(json.dumps(emit_schema(), indent=2))
    elif args.check:
        sys.exit(load_and_check(args.check, merge=args.merge))
    else:
        parser.print_help()
