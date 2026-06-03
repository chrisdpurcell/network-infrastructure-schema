#!/usr/bin/env python3
"""Builder for schemas/infra.schema.json.

This script is NOT part of the shipped deliverable; it is the single source
that emits the canonical hand-authored JSON Schema (Draft 2020-12). Authoring
the schema as a Python dict and serializing it keeps brackets/commas correct
and lets us reuse $def fragments without copy/paste drift.
"""
import json
import pathlib

SCHEMA_ID = "https://schemas.luminous3d.example/infra/v1alpha1/infra.schema.json"
API_VERSION = "infra.luminous3d.example/v1alpha1"

KINDS = [
    "Site", "NetworkZone", "Vlan", "Prefix", "Gateway", "Device", "Interface",
    "ProxmoxCluster", "Host", "VirtualMachine", "LxcContainer", "Service",
    "ServiceDependency", "FirewallPolicy", "AllowedFlow", "BackupClass",
    "SecretRef", "MonitoringCheck", "FailureScenario",
]

# ---------------------------------------------------------------------------
# Reusable primitive $defs
# ---------------------------------------------------------------------------
SLUG = {
    "type": "string",
    "description": "DNS-1123 label: lowercase alphanumerics and '-', 1-63 chars.",
    "pattern": r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$",
    "minLength": 1,
    "maxLength": 63,
}

defs = {}

defs["Slug"] = SLUG

defs["ApiVersion"] = {
    "type": "string",
    "description": "Group/version, e.g. infra.luminous3d.example/v1alpha1.",
    "pattern": r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?/v[0-9]+((alpha|beta)[0-9]+)?$",
}

defs["Kind"] = {"type": "string", "enum": KINDS}

defs["Labels"] = {
    "type": "object",
    "description": "Open key/value extension point. Keys are slug-like; values free-form strings.",
    "propertyNames": {"pattern": r"^[a-zA-Z0-9]([a-zA-Z0-9_./-]{0,61}[a-zA-Z0-9])?$"},
    "additionalProperties": {"type": "string"},
}

defs["Metadata"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name"],
    "properties": {
        "name": {"$ref": "#/$defs/Slug"},
        "namespace": {"$ref": "#/$defs/Slug", "default": "default"},
        "uid": {
            "type": "string",
            "description": "Optional stable identifier. NOT used for authored references; refs use kind+name.",
        },
        "title": {"type": "string"},
        "description": {"type": "string"},
        "owner": {"type": "string", "description": "Owning person/team, free-form."},
        "labels": {"$ref": "#/$defs/Labels"},
        "annotations": {"$ref": "#/$defs/Labels"},
    },
}

defs["ObjectRef"] = {
    "type": "object",
    "description": "Reference to another object by composite key (kind + name [+ namespace]).",
    "additionalProperties": False,
    "required": ["kind", "name"],
    "properties": {
        "kind": {"$ref": "#/$defs/Kind"},
        "name": {"$ref": "#/$defs/Slug"},
        "namespace": {"$ref": "#/$defs/Slug"},
    },
}

defs["SecretRefInline"] = {
    "type": "object",
    "description": (
        "Inline pointer to a secret stored in an external backend. "
        "NEVER carries the secret value. Either references a SecretRef object "
        "by name, or names provider+path directly."
    ),
    "additionalProperties": False,
    "properties": {
        "ref": {"$ref": "#/$defs/Slug", "description": "Name of a SecretRef-kind object."},
        "provider": {
            "type": "string",
            "enum": ["openbao", "vault", "sops", "onepassword", "env", "file"],
        },
        "path": {"type": "string", "description": "Backend path/identifier, e.g. kv/data/infra/pve."},
        "key": {"type": "string", "description": "Field within the secret to select."},
    },
    "not": {"required": ["value"]},
    "anyOf": [
        {"required": ["ref"]},
        {"required": ["provider", "path"]},
    ],
}

defs["Cidr"] = {
    "type": "string",
    "description": "IPv4 or IPv6 network in CIDR notation.",
    "anyOf": [
        {"pattern": r"^((25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)/(3[0-2]|[12]?\d)$"},
        {"pattern": r"^([0-9a-fA-F:]+)/(12[0-8]|1[01]\d|[1-9]?\d)$"},
    ],
}

defs["IpAddress"] = {
    "type": "string",
    "anyOf": [{"format": "ipv4"}, {"format": "ipv6"}],
}

defs["IpOrDhcp"] = {
    "anyOf": [
        {"const": "dhcp"},
        {"$ref": "#/$defs/Cidr"},
    ],
}

defs["MacAddress"] = {
    "type": "string",
    "pattern": r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$",
}

defs["Port"] = {"type": "integer", "minimum": 1, "maximum": 65535}

defs["L4Protocol"] = {"type": "string", "enum": ["tcp", "udp", "sctp", "icmp", "any"]}

defs["Criticality"] = {"type": "string", "enum": ["low", "medium", "high", "critical"]}

defs["TrustLevel"] = {
    "type": "string",
    "enum": ["management", "trusted", "user", "guest", "iot", "dmz", "untrusted"],
}

defs["Duration"] = {
    "type": "string",
    "description": "Go-style duration, e.g. 30s, 5m, 1h, 24h.",
    "pattern": r"^[0-9]+(ms|s|m|h|d)$",
}

defs["PortSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["protocol", "port"],
    "properties": {
        "name": {"type": "string"},
        "protocol": {"$ref": "#/$defs/L4Protocol"},
        "port": {"$ref": "#/$defs/Port"},
    },
}

defs["IpConfig"] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "address": {"$ref": "#/$defs/IpOrDhcp"},
        "gateway": {"$ref": "#/$defs/IpAddress"},
    },
}

defs["GuestNic"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "bridge"],
    "properties": {
        "name": {"type": "string", "description": "Guest-side name, e.g. eth0/net0/veth0."},
        "bridge": {"type": "string", "description": "Proxmox bridge, e.g. vmbr0."},
        "model": {"type": "string", "enum": ["virtio", "e1000", "rtl8139", "vmxnet3"], "default": "virtio"},
        "mac": {"$ref": "#/$defs/MacAddress"},
        "mtu": {"type": "integer", "minimum": 576, "maximum": 9000},
        "vlan": {
            "description": "Tagged VLAN: either a VLAN id (1-4094) or an ObjectRef to a Vlan object.",
            "oneOf": [
                {"type": "integer", "minimum": 1, "maximum": 4094},
                {"$ref": "#/$defs/ObjectRef"},
            ],
        },
        "ipv4": {"$ref": "#/$defs/IpConfig"},
        "ipv6": {"$ref": "#/$defs/IpConfig"},
        "firewall": {"type": "boolean", "default": True},
    },
}

defs["DiskSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["id", "datastore", "sizeGb"],
    "properties": {
        "id": {"type": "string", "description": "Logical disk id, e.g. scsi0/virtio0/rootfs."},
        "datastore": {"type": "string"},
        "sizeGb": {"type": "integer", "minimum": 1},
        "interface": {"type": "string", "enum": ["scsi", "virtio", "sata", "ide"]},
        "iothread": {"type": "boolean"},
        "discard": {"type": "boolean"},
        "ssd": {"type": "boolean"},
    },
}

defs["MountPoint"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["path"],
    "properties": {
        "volume": {"type": "string", "description": "Datastore id (managed volume) or host path (bind mount)."},
        "path": {"type": "string", "description": "In-guest mount path."},
        "sizeGb": {"type": "integer", "minimum": 1},
        "backup": {"type": "boolean", "default": False},
        "readOnly": {"type": "boolean", "default": False},
        "bind": {"type": "boolean", "default": False, "description": "True for host bind mount (requires root@pam)."},
    },
}

defs["ExposureDecision"] = {
    "type": "object",
    "description": "Explicit, auditable decision about how far a service is reachable.",
    "additionalProperties": False,
    "required": ["level"],
    "properties": {
        "level": {"type": "string", "enum": ["internal", "lan", "vpn", "public"]},
        "approved": {"type": "boolean", "default": False},
        "approvedBy": {"type": "string"},
        "reason": {"type": "string"},
    },
}

defs["FlowEndpoint"] = {
    "type": "object",
    "description": "One side of an allowed flow. At least one selector must be set.",
    "additionalProperties": False,
    "minProperties": 1,
    "properties": {
        "zone": {"$ref": "#/$defs/ObjectRef"},
        "prefix": {"$ref": "#/$defs/ObjectRef"},
        "cidr": {"$ref": "#/$defs/Cidr"},
        "service": {"$ref": "#/$defs/ObjectRef"},
        "any": {"type": "boolean"},
    },
}

# ---------------------------------------------------------------------------
# Per-kind spec $defs
# ---------------------------------------------------------------------------

defs["SiteSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["role"],
    "properties": {
        "displayName": {"type": "string"},
        "role": {"type": "string", "enum": ["home", "offsite", "cloud", "edge"]},
        "location": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "facility": {"type": "string"},
                "city": {"type": "string"},
                "region": {"type": "string"},
                "country": {"type": "string"},
                "timezone": {"type": "string"},
            },
        },
        "notes": {"type": "string"},
    },
}

defs["NetworkZoneSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site", "trustLevel"],
    "properties": {
        "site": {"$ref": "#/$defs/ObjectRef"},
        "trustLevel": {"$ref": "#/$defs/TrustLevel"},
        "defaultDeny": {"type": "boolean", "default": True},
        "description": {"type": "string"},
    },
}

defs["VlanSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site", "vlanId", "vlanName"],
    "properties": {
        "site": {"$ref": "#/$defs/ObjectRef"},
        "zone": {"$ref": "#/$defs/ObjectRef"},
        "vlanId": {"type": "integer", "minimum": 1, "maximum": 4094},
        "vlanName": {"type": "string"},
        "description": {"type": "string"},
    },
}

defs["PrefixSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cidr"],
    "properties": {
        "cidr": {"$ref": "#/$defs/Cidr"},
        "site": {"$ref": "#/$defs/ObjectRef"},
        "vlan": {"$ref": "#/$defs/ObjectRef"},
        "role": {
            "type": "string",
            "enum": ["management", "server", "user", "guest", "iot", "dmz",
                     "loopback", "transit", "container", "storage"],
        },
        "gateway": {"$ref": "#/$defs/IpAddress"},
        "dhcp": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "ranges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["start", "end"],
                        "properties": {
                            "start": {"$ref": "#/$defs/IpAddress"},
                            "end": {"$ref": "#/$defs/IpAddress"},
                        },
                    },
                },
            },
        },
        "description": {"type": "string"},
    },
}

defs["GatewaySpec"] = {
    "type": "object",
    "description": "Logical default-route target (L3 next-hop) for a prefix.",
    "additionalProperties": False,
    "required": ["prefix", "address"],
    "properties": {
        "prefix": {"$ref": "#/$defs/ObjectRef"},
        "address": {"$ref": "#/$defs/IpAddress"},
        "device": {"$ref": "#/$defs/ObjectRef"},
        "interface": {"$ref": "#/$defs/ObjectRef"},
        "vrrp": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "group": {"type": "integer", "minimum": 1, "maximum": 255},
                "priority": {"type": "integer", "minimum": 1, "maximum": 254},
                "virtualAddress": {"$ref": "#/$defs/IpAddress"},
            },
        },
        "description": {"type": "string"},
    },
}

defs["DeviceSpec"] = {
    "type": "object",
    "description": "Physical/network hardware tracked in DCIM (router, switch, firewall, server chassis, PDU).",
    "additionalProperties": False,
    "required": ["site", "role"],
    "properties": {
        "site": {"$ref": "#/$defs/ObjectRef"},
        "role": {
            "type": "string",
            "enum": ["router", "switch", "firewall", "ap", "server",
                     "appliance", "pdu", "storage", "other"],
        },
        "manufacturer": {"type": "string"},
        "model": {"type": "string"},
        "platform": {"type": "string", "description": "OS/NOS family, e.g. proxmox, opnsense, mikrotik, edgeos."},
        "serialNumber": {"type": "string"},
        "managementIp": {"$ref": "#/$defs/IpAddress"},
    },
}

defs["InterfaceSpec"] = {
    "type": "object",
    "description": "A port on a Device (physical, LAG, VLAN sub-if, loopback, or mgmt).",
    "additionalProperties": False,
    "required": ["device", "ifName", "type"],
    "properties": {
        "device": {"$ref": "#/$defs/ObjectRef"},
        "ifName": {"type": "string"},
        "type": {"type": "string", "enum": ["physical", "lag", "vlan", "virtual", "mgmt", "loopback"]},
        "enabled": {"type": "boolean", "default": True},
        "mac": {"$ref": "#/$defs/MacAddress"},
        "mtu": {"type": "integer", "minimum": 576, "maximum": 9216},
        "mode": {"type": "string", "enum": ["access", "tagged", "tagged-all", "routed"]},
        "untaggedVlan": {"$ref": "#/$defs/ObjectRef"},
        "taggedVlans": {"type": "array", "items": {"$ref": "#/$defs/ObjectRef"}},
        "addresses": {"type": "array", "items": {"$ref": "#/$defs/Cidr"}},
        "lagMembers": {"type": "array", "items": {"$ref": "#/$defs/ObjectRef"}},
        "description": {"type": "string"},
    },
}

defs["ProxmoxClusterSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["site", "nodes"],
    "properties": {
        "site": {"$ref": "#/$defs/ObjectRef"},
        "nodes": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/ObjectRef"}},
        "quorumExpected": {"type": "integer", "minimum": 1},
        "apiEndpoint": {"type": "string", "format": "uri"},
        "tokenRef": {"$ref": "#/$defs/SecretRefInline"},
        "description": {"type": "string"},
    },
}

defs["HostSpec"] = {
    "type": "object",
    "description": "A physical machine that runs workloads (hypervisor node or bare-metal service host).",
    "additionalProperties": False,
    "required": ["site", "role"],
    "properties": {
        "site": {"$ref": "#/$defs/ObjectRef"},
        "cluster": {"$ref": "#/$defs/ObjectRef"},
        "device": {"$ref": "#/$defs/ObjectRef", "description": "Link to the DCIM hardware record."},
        "role": {"type": "string", "enum": ["hypervisor", "baremetal-service", "storage", "other"]},
        "proxmoxNode": {"type": "string", "description": "PVE node name (node_name in the provider)."},
        "cpuCores": {"type": "integer", "minimum": 1},
        "memoryMb": {"type": "integer", "minimum": 256},
        "managementIp": {"$ref": "#/$defs/IpAddress"},
        "storage": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id"],
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string", "enum": ["lvm", "lvmthin", "zfs", "dir", "nfs", "cephfs", "rbd"]},
                    "sizeGb": {"type": "integer", "minimum": 1},
                },
            },
        },
    },
}

_GUEST_COMMON = {
    "host": {"$ref": "#/$defs/ObjectRef"},
    "cluster": {"$ref": "#/$defs/ObjectRef"},
    "proxmoxNode": {"type": "string"},
    "vmId": {"type": "integer", "minimum": 100, "maximum": 999999999},
    "cores": {"type": "integer", "minimum": 1},
    "memoryMb": {"type": "integer", "minimum": 16},
    "networkInterfaces": {"type": "array", "items": {"$ref": "#/$defs/GuestNic"}},
    "startOnBoot": {"type": "boolean", "default": True},
    "tags": {"type": "array", "items": {"type": "string"}},
    "description": {"type": "string"},
}

defs["VirtualMachineSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cores", "memoryMb"],
    "properties": {
        **_GUEST_COMMON,
        "template": {"type": "string", "description": "Clone source name/id, or download-file reference."},
        "osType": {"type": "string", "description": "Proxmox ostype, e.g. l26, win11."},
        "disks": {"type": "array", "items": {"$ref": "#/$defs/DiskSpec"}},
        "agent": {"type": "boolean", "default": True},
        "cloudInit": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "username": {"type": "string"},
                "sshKeysRef": {"$ref": "#/$defs/SecretRefInline"},
                "passwordRef": {"$ref": "#/$defs/SecretRefInline"},
                "userDataFileId": {"type": "string"},
                "datastore": {"type": "string"},
            },
        },
    },
}

defs["LxcContainerSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["cores", "memoryMb", "ostemplate"],
    "properties": {
        **_GUEST_COMMON,
        "ostemplate": {"type": "string", "description": "CT template volume id or download-file reference."},
        "osType": {"type": "string", "description": "Provider operating_system.type, e.g. ubuntu, debian, alpine."},
        "unprivileged": {"type": "boolean", "default": True},
        "features": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "nesting": {"type": "boolean", "default": False},
                "fuse": {"type": "boolean", "default": False},
                "keyctl": {"type": "boolean", "default": False},
            },
        },
        "swapMb": {"type": "integer", "minimum": 0},
        "rootfs": {"$ref": "#/$defs/DiskSpec"},
        "mounts": {"type": "array", "items": {"$ref": "#/$defs/MountPoint"}},
        "cpuUnits": {"type": "integer", "minimum": 0},
        "sshKeysRef": {"$ref": "#/$defs/SecretRefInline"},
        "passwordRef": {"$ref": "#/$defs/SecretRefInline"},
    },
}

defs["ServiceSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["runsOn", "exposure"],
    "properties": {
        "runsOn": {"$ref": "#/$defs/ObjectRef", "description": "VirtualMachine, LxcContainer, or Host that hosts the service."},
        "serviceType": {
            "type": "string",
            "enum": ["web", "db", "dns", "dhcp", "monitoring", "storage",
                     "automation", "proxy", "auth", "messaging", "other"],
        },
        "criticality": {"$ref": "#/$defs/Criticality"},
        "ports": {"type": "array", "items": {"$ref": "#/$defs/PortSpec"}},
        "vip": {"$ref": "#/$defs/IpAddress"},
        "fqdn": {"type": "string", "format": "hostname"},
        "exposure": {"$ref": "#/$defs/ExposureDecision"},
        "backupClass": {"$ref": "#/$defs/ObjectRef"},
        "healthcheck": {"$ref": "#/$defs/ObjectRef"},
        "secrets": {"type": "array", "items": {"$ref": "#/$defs/SecretRefInline"}},
        "implementation": {
            "type": "object",
            "description": "How the service is realized. Example only; does not shape the desired-state core.",
            "additionalProperties": False,
            "required": ["type"],
            "properties": {
                "type": {"type": "string", "enum": ["docker-compose", "native", "systemd", "helm"]},
                "composeServiceName": {"type": "string"},
                "composeFile": {"type": "string"},
                "image": {"type": "string"},
                "unitName": {"type": "string"},
            },
        },
    },
}

defs["ServiceDependencySpec"] = {
    "type": "object",
    "description": "Directed edge in the service dependency graph (from -> to).",
    "additionalProperties": False,
    "required": ["from", "to", "type"],
    "properties": {
        "from": {"$ref": "#/$defs/ObjectRef"},
        "to": {"$ref": "#/$defs/ObjectRef"},
        "type": {"type": "string", "enum": ["requires", "soft-requires", "uses"]},
        "protocol": {"$ref": "#/$defs/L4Protocol"},
        "port": {"$ref": "#/$defs/Port"},
        "description": {"type": "string"},
    },
}

defs["FirewallPolicySpec"] = {
    "type": "object",
    "description": "Firewall posture/ownership: default action and scope for a set of AllowedFlow rules.",
    "additionalProperties": False,
    "required": ["defaultAction", "appliesTo"],
    "properties": {
        "defaultAction": {"type": "string", "enum": ["drop", "reject", "accept"]},
        "appliesTo": {"type": "string", "enum": ["zone-pair", "device", "global"]},
        "device": {"$ref": "#/$defs/ObjectRef"},
        "fromZone": {"$ref": "#/$defs/ObjectRef"},
        "toZone": {"$ref": "#/$defs/ObjectRef"},
        "description": {"type": "string"},
    },
}

defs["AllowedFlowSpec"] = {
    "type": "object",
    "description": "A single permitted flow (explicit exception to default-deny).",
    "additionalProperties": False,
    "required": ["policy", "source", "destination", "protocol"],
    "properties": {
        "policy": {"$ref": "#/$defs/ObjectRef"},
        "source": {"$ref": "#/$defs/FlowEndpoint"},
        "destination": {"$ref": "#/$defs/FlowEndpoint"},
        "protocol": {"$ref": "#/$defs/L4Protocol"},
        "ports": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"$ref": "#/$defs/Port"},
                    {"type": "string", "pattern": r"^[0-9]{1,5}-[0-9]{1,5}$"},
                ]
            },
        },
        "action": {"type": "string", "enum": ["allow"], "default": "allow"},
        "logging": {"type": "boolean", "default": False},
        "description": {"type": "string"},
    },
}

defs["BackupClassSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schedule", "target", "retention"],
    "properties": {
        "schedule": {"type": "string", "description": "Cron expression or named tier, e.g. '0 2 * * *' or 'daily'."},
        "target": {"type": "string", "description": "Backend, e.g. pbs:main, restic:b2, nfs:nas01."},
        "restoreTarget": {"type": "string", "description": "Where restores land; required for critical services (policy-enforced)."},
        "retention": {
            "type": "object",
            "additionalProperties": False,
            "minProperties": 1,
            "properties": {
                "daily": {"type": "integer", "minimum": 0},
                "weekly": {"type": "integer", "minimum": 0},
                "monthly": {"type": "integer", "minimum": 0},
                "yearly": {"type": "integer", "minimum": 0},
            },
        },
        "rpoMinutes": {"type": "integer", "minimum": 0},
        "rtoMinutes": {"type": "integer", "minimum": 0},
        "encryptionSecretRef": {"$ref": "#/$defs/SecretRefInline"},
        "description": {"type": "string"},
    },
}

defs["SecretRefSpec"] = {
    "type": "object",
    "description": "Catalog entry for a secret stored in an external backend. NEVER contains the secret value.",
    "additionalProperties": False,
    "required": ["provider", "path"],
    "properties": {
        "provider": {"type": "string", "enum": ["openbao", "vault", "sops", "onepassword", "env", "file"]},
        "path": {"type": "string"},
        "keys": {"type": "array", "items": {"type": "string"}},
        "rotation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "intervalDays": {"type": "integer", "minimum": 1},
            },
        },
        "description": {"type": "string"},
    },
    "not": {"required": ["value"]},
}

defs["MonitoringCheckSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["target", "type", "interval"],
    "properties": {
        "target": {"$ref": "#/$defs/ObjectRef"},
        "type": {"type": "string", "enum": ["http", "https", "tcp", "icmp", "dns", "script", "snmp"]},
        "interval": {"$ref": "#/$defs/Duration"},
        "timeout": {"$ref": "#/$defs/Duration"},
        "severity": {"$ref": "#/$defs/Criticality"},
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "url": {"type": "string"},
                "port": {"$ref": "#/$defs/Port"},
                "expectStatus": {"type": "integer"},
                "expectString": {"type": "string"},
                "query": {"type": "string"},
                "scriptPath": {"type": "string"},
            },
        },
        "notify": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
    },
}

defs["FailureScenarioSpec"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["fault", "expected"],
    "properties": {
        "description": {"type": "string"},
        "fault": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "targets"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["host-down", "device-down", "link-down", "service-down", "site-down", "wan-down"],
                },
                "targets": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/ObjectRef"}},
            },
        },
        "expected": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "unavailableServices": {"type": "array", "items": {"$ref": "#/$defs/ObjectRef"}},
                "degradedServices": {"type": "array", "items": {"$ref": "#/$defs/ObjectRef"}},
                "failover": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["service", "to"],
                        "properties": {
                            "service": {"$ref": "#/$defs/ObjectRef"},
                            "to": {"$ref": "#/$defs/ObjectRef"},
                            "automatic": {"type": "boolean", "default": False},
                        },
                    },
                },
                "maxOutageMinutes": {"type": "integer", "minimum": 0},
            },
        },
        "validation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["tool"],
            "properties": {
                "tool": {"type": "string", "enum": ["batfish", "containerlab", "manual"]},
                "notes": {"type": "string"},
            },
        },
    },
}

# Map kind -> spec $def
KIND_SPEC = {
    "Site": "SiteSpec",
    "NetworkZone": "NetworkZoneSpec",
    "Vlan": "VlanSpec",
    "Prefix": "PrefixSpec",
    "Gateway": "GatewaySpec",
    "Device": "DeviceSpec",
    "Interface": "InterfaceSpec",
    "ProxmoxCluster": "ProxmoxClusterSpec",
    "Host": "HostSpec",
    "VirtualMachine": "VirtualMachineSpec",
    "LxcContainer": "LxcContainerSpec",
    "Service": "ServiceSpec",
    "ServiceDependency": "ServiceDependencySpec",
    "FirewallPolicy": "FirewallPolicySpec",
    "AllowedFlow": "AllowedFlowSpec",
    "BackupClass": "BackupClassSpec",
    "SecretRef": "SecretRefSpec",
    "MonitoringCheck": "MonitoringCheckSpec",
    "FailureScenario": "FailureScenarioSpec",
}

# ---------------------------------------------------------------------------
# Object (single envelope) and Bundle definitions
# ---------------------------------------------------------------------------
discriminator_allof = []
for kind, spec in KIND_SPEC.items():
    discriminator_allof.append({
        "if": {"properties": {"kind": {"const": kind}}, "required": ["kind"]},
        "then": {"properties": {"spec": {"$ref": f"#/$defs/{spec}"}}},
    })

defs["Object"] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"$ref": "#/$defs/ApiVersion"},
        "kind": {"$ref": "#/$defs/Kind"},
        "metadata": {"$ref": "#/$defs/Metadata"},
        "spec": {"type": "object"},
    },
    "allOf": discriminator_allof,
}

defs["Bundle"] = {
    "type": "object",
    "description": "Multi-object manifest: a container whose spec.items is an array of Objects.",
    "additionalProperties": False,
    "required": ["apiVersion", "kind", "metadata", "spec"],
    "properties": {
        "apiVersion": {"$ref": "#/$defs/ApiVersion"},
        "kind": {"const": "InfraManifest"},
        "metadata": {"$ref": "#/$defs/Metadata"},
        "spec": {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {
                "items": {"type": "array", "minItems": 1, "items": {"$ref": "#/$defs/Object"}},
            },
        },
    },
}

schema = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": SCHEMA_ID,
    "title": "Luminous3D Desired-State Infrastructure Model",
    "description": (
        "Canonical validation schema for hand-authored desired-state YAML. "
        "A document is either a single Object or an InfraManifest Bundle. "
        "Multi-document YAML streams are split by the harness and each document "
        "is validated against this schema."
    ),
    "oneOf": [
        {"$ref": "#/$defs/Object"},
        {"$ref": "#/$defs/Bundle"},
    ],
    "$defs": defs,
}

out = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "infra.schema.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(schema, indent=2) + "\n")
print(f"wrote {out} ({out.stat().st_size} bytes)")
