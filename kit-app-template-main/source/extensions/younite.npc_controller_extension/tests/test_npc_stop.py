"""
NPC Controller — Stop & Cleanup
================================
Paste into Script Editor to stop all NPCs and remove the test capsule.
"""
import omni.usd
from younite.messaging_core_extension.message_utils import dispatch_to_events2

# Stop all NPC movement
dispatch_to_events2("npcStop", {"all": True})
print("[test] All NPCs stopped")

# Remove test capsule
stage = omni.usd.get_context().get_stage()
if stage:
    prim = stage.GetPrimAtPath("/World/TestNpc")
    if prim and prim.IsValid():
        stage.RemovePrim("/World/TestNpc")
        print("[test] Removed /World/TestNpc")
