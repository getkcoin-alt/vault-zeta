from pathlib import Path
from tempfile import TemporaryDirectory

from vault_zeta import VaultZetaStore


with TemporaryDirectory(prefix="vault-zeta-") as temp:
    db = Path(temp) / "zeta.db"

    with VaultZetaStore(db) as zeta:
        zeta.add_memory(
            kind="semantic",
            content="CANOPY greenhouse zone 7 prefers a soil-moisture target above 30 percent.",
            scope="canopy/greenhouse",
            source="greenhouse-policy.md",
            source_fingerprint="sha256:demo",
            confidence=0.94,
            metadata={"owner": "demo"},
        )

        zeta.append_event(
            mission_id="canopy-demo",
            event_type="observation",
            payload={"zone": 7, "soil_moisture": 0.22},
        )

        zeta.save_mission(
            "canopy-demo",
            status="running",
            snapshot={"next_step": "review irrigation threshold", "zone": 7},
        )

        print("Memory results:")
        for item in zeta.search("soil moisture", scope="canopy/greenhouse"):
            print(f"- {item.content} (confidence={item.confidence})")

        print("\nMission events:")
        for event in zeta.events("canopy-demo"):
            print(f"- #{event.seq} {event.event_type}: {event.payload}")

        print("\nSnapshot:")
        print(zeta.load_mission("canopy-demo"))
