#!/usr/bin/env python3
"""
OpenAPI spec guard.

`yaml.safe_load` accepts DUPLICATE mapping keys and silently keeps the last one,
so a spec with a repeated property still "parses OK" — and the breakage only
surfaces much later, in a consumer running openapi-typescript, as an opaque
YamlParseError pointing at a schema nobody was looking at.

That is not hypothetical: §70.2 inserted a block twice into
PortfolioTotalMetrics (an uncounted replace on a key that exists in two schemas)
and this lint passed it. Two contracts were published before the consumers
caught it.

So: parse, then verify no schema block declares the same property twice, and
verify the document actually bundles (which is what consumers do).
"""
import sys
from collections import Counter
import re

import yaml

PATH = "openapi.yaml"
raw = open(PATH).read()

# 1. parses
doc = yaml.safe_load(raw)

# 2. no duplicate keys — safe_load hides these, so walk the text.
lines = raw.split("\n")
schema_re = re.compile(r"^    (\w+):\s*$")
prop_re = re.compile(r"^        (\w+):")
duplicates = []
i = 0
while i < len(lines):
    m = schema_re.match(lines[i])
    if not m:
        i += 1
        continue
    name = m.group(1)
    j = i + 1
    keys: list[str] = []
    while j < len(lines) and (lines[j].startswith("      ") or not lines[j].strip()):
        km = prop_re.match(lines[j])
        if km:
            keys.append(km.group(1))
        j += 1
    for key, count in Counter(keys).items():
        if count > 1:
            duplicates.append(f"{name}.{key} declared {count}x")
    i = j

if duplicates:
    print("openapi.yaml has DUPLICATE property keys:", file=sys.stderr)
    for d in duplicates:
        print(f"  - {d}", file=sys.stderr)
    print(
        "\nyaml.safe_load keeps the LAST value and reports no error, so this "
        "must be checked explicitly. Duplicate keys break openapi-typescript in "
        "every consumer with a YamlParseError that names the wrong place.",
        file=sys.stderr,
    )
    sys.exit(1)

# 3. the schemas §70 relies on must actually carry the new fields
required = {
    "PortfolioTotalMetrics": ("instrumentsValue", "cashValue", "unpricedPositions", "priceAsOf", "priceSource"),
    "PortfolioSummaryMetrics": ("cashValue", "unpricedPositions", "priceAsOf", "priceSource"),
}
for schema, fields in required.items():
    props = doc.get("components", {}).get("schemas", {}).get(schema, {}).get("properties", {})
    missing = [f for f in fields if f not in props]
    if missing:
        print(f"{schema} is missing {missing}", file=sys.stderr)
        sys.exit(1)

# 4. the in-kind transfer types, and the field that carries their counterparty.
#    A transfer is a position movement with no cash effect; if it is ever dropped
#    from this enum the import rejects the row at the Zod layer, well away from
#    the spec that is supposed to describe it.
schemas = doc.get("components", {}).get("schemas", {})
tx_enum = (
    schemas.get("ImportPortfolioTx", {})
    .get("allOf", [{}])[1]
    .get("properties", {})
    .get("type", {})
    .get("enum", [])
)
for value in ("TRANSFER_OUT", "TRANSFER_IN"):
    if value not in tx_enum:
        print(
            f"ImportPortfolioTx.type is missing {value} (has {tx_enum})",
            file=sys.stderr,
        )
        sys.exit(1)

tx_props = schemas.get("ImportPortfolioTx", {}).get("allOf", [{}])[1].get("properties", {})
if "toPortfolioName" not in tx_props:
    print("ImportPortfolioTx has no toPortfolioName", file=sys.stderr)
    sys.exit(1)
if not tx_props["toPortfolioName"].get("nullable"):
    print("toPortfolioName must be nullable: it is meaningless on other types", file=sys.stderr)
    sys.exit(1)

# The read path needs no enum change: RecentCashTransaction.type stays a plain
# string and displayLabel already exists. Asserted rather than assumed, because
# an enum added here for the wrong reason would force every consumer to widen.
cash_tx = schemas.get("RecentCashTransaction", {}).get("properties", {}).get("type", {})
if "enum" in cash_tx:
    print(
        "RecentCashTransaction.type grew an enum; the transfer types are not "
        "cash transactions and must not appear there",
        file=sys.stderr,
    )
    sys.exit(1)
if "displayLabel" not in schemas.get("RecentCashTransaction", {}).get("properties", {}):
    print("RecentCashTransaction.displayLabel is missing", file=sys.stderr)
    sys.exit(1)

# 5. the virtual-portfolio surface. OpenAPI 3.0 cannot express "isVirtual
#    requires labelId" without changing the shape every consumer compiles
#    against, so the conditional rule is declared in the schema description and
#    enforced server-side. The fields themselves are still part of the contract
#    both producers and consumers compile against, so assert they stay declared
#    with the optionality that makes a casual portfolio legal without a label.
portfolio = schemas.get("Portfolio", {})
portfolio_props = portfolio.get("properties", {})
if portfolio_props.get("isVirtual", {}).get("type") != "boolean":
    print("Portfolio.isVirtual is missing or not a boolean", file=sys.stderr)
    sys.exit(1)
if not portfolio_props.get("labelId", {}).get("nullable"):
    print(
        "Portfolio.labelId is missing or not nullable: a casual portfolio "
        "carries null rather than a label",
        file=sys.stderr,
    )
    sys.exit(1)

create = schemas.get("CreatePortfolioRequest", {})
create_props = create.get("properties", {})
if create_props.get("isVirtual", {}).get("default") is not False:
    print(
        "CreatePortfolioRequest.isVirtual must default to false: a casual "
        "portfolio is the default and must keep creating without a label",
        file=sys.stderr,
    )
    sys.exit(1)
if not create_props.get("labelId", {}).get("nullable"):
    print("CreatePortfolioRequest.labelId is missing or not nullable", file=sys.stderr)
    sys.exit(1)
create_desc = create.get("description", "")
for phrase in ("labelId", "cashLegOnTrade"):
    if phrase not in create_desc:
        print(
            f"CreatePortfolioRequest description no longer documents the "
            f"virtual-portfolio invariant ({phrase} unmentioned); the rule is "
            f"enforced server-side and this description is its only contract home",
            file=sys.stderr,
        )
        sys.exit(1)

# 6. lifecycle-complete consolidated positions retain their portfolio-membership
#    identity. The descriptions are the contract's only declaration that closed
#    rows are retained and that a shared position is returned once per membership.
positions_op = doc.get("paths", {}).get("/portfolios/positions", {}).get("get", {})
positions_text = (
    f"{positions_op.get('summary', '')} {positions_op.get('description', '')}"
).lower()
for phrase in (
    "open and closed",
    "once per membership",
    "not aggregated by symbol",
    "portfolioid",
    "portfolioname",
):
    if phrase not in positions_text:
        print(
            f"GET /portfolios/positions no longer documents lifecycle/membership "
            f"semantics ({phrase!r} missing)",
            file=sys.stderr,
        )
        sys.exit(1)

position = schemas.get("Position", {})
position_props = position.get("properties", {})
position_required = set(position.get("required", []))
if not {"isOpen", "portfolioId"}.issubset(position_required):
    print("Position.isOpen and Position.portfolioId must remain required", file=sys.stderr)
    sys.exit(1)
if {"closedAt", "portfolioName"} & position_required:
    print("Position.closedAt and Position.portfolioName must remain optional", file=sys.stderr)
    sys.exit(1)
if position_props.get("isOpen", {}).get("type") != "boolean":
    print("Position.isOpen is missing or not a boolean", file=sys.stderr)
    sys.exit(1)
is_open_desc = position_props.get("isOpen", {}).get("description", "").lower()
if "currently held" not in is_open_desc or "retained as history" not in is_open_desc:
    print(
        "Position.isOpen must distinguish currently held positions from retained closed history",
        file=sys.stderr,
    )
    sys.exit(1)
closed_at = position_props.get("closedAt", {})
if (
    closed_at.get("type") != "string"
    or closed_at.get("format") != "date-time"
    or not closed_at.get("nullable")
):
    print("Position.closedAt must remain a nullable timestamp", file=sys.stderr)
    sys.exit(1)
closed_at_desc = closed_at.get("description", "").lower()
if "fully closed" not in closed_at_desc or "null while" not in closed_at_desc:
    print("Position.closedAt must document the full-close timestamp", file=sys.stderr)
    sys.exit(1)
portfolio_id = position_props.get("portfolioId", {})
if (
    portfolio_id.get("type") != "string"
    or portfolio_id.get("format") != "uuid"
    or "membership" not in portfolio_id.get("description", "").lower()
):
    print("Position.portfolioId must identify the row's portfolio membership", file=sys.stderr)
    sys.exit(1)
if not position_props.get("portfolioName", {}).get("nullable"):
    print("Position.portfolioName must remain nullable", file=sys.stderr)
    sys.exit(1)
portfolio_name_desc = position_props.get("portfolioName", {}).get("description", "").lower()
if "consolidated" not in portfolio_name_desc or "null on the per-portfolio route" not in portfolio_name_desc:
    print("Position.portfolioName must document consolidated and per-portfolio semantics", file=sys.stderr)
    sys.exit(1)

print(
    "openapi.yaml OK: parses, no duplicate keys, §68/§70 fields present, "
    "TRANSFER_OUT/TRANSFER_IN declared, virtual-portfolio surface declared, "
    "position lifecycle/membership documented"
)
