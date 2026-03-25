# WhatsApp Dedicated Account Migration

The current WhatsApp path is a bootstrap path, not the final product shape.

Current bootstrap posture:
- linked to the operator's personal number
- `selfChatMode: true`
- useful for bring-up and rapid debugging
- bad fit for shared use by Grossberg or other researchers

Why the bootstrap path is not enough:
- self-chat can echo replies back into OpenClaw and create loops
- the assistant identity is tied to one person instead of the lab
- access control is awkward for multiple researchers
- the user experience feels like a debug bridge instead of a shared lab assistant

Target posture:
- dedicated WhatsApp account
- dedicated phone number owned by the lab or a stable lab-admin path
- `selfChatMode: false`
- approved human users message the assistant as a normal contact
- OpenClaw acts as a shared lab-assistant front door

Minimum migration plan:
1. Register or activate the dedicated phone number.
2. Create or register a dedicated WhatsApp account on that number.
3. Update the local non-committed OpenClaw secret on `.44` so `OPENCLAW_WHATSAPP_OWNER` matches the dedicated assistant number.
4. Change the exported WhatsApp channel policy so `selfChatMode` is disabled for the real assistant path.
5. Re-export and restart OpenClaw.
6. Link the new WhatsApp account from the live pod.
7. Expand the allowlist to approved researchers as needed.
8. Validate real round-trip messaging from a human account that is not the assistant account itself.

Recommended policy changes for the dedicated account path:
- `selfChatMode: false`
- keep `dmPolicy: allowlist`
- keep `groupPolicy: disabled` at first
- allow only explicitly approved human numbers during the first shared rollout

Recommended rollout order:
1. Keep the current self-chat path only long enough to finish UX debugging.
2. Move to the dedicated number before treating WhatsApp as the real researcher-facing assistant surface.
3. Only after the dedicated-number path is stable, consider broader allowlist expansion or group-chat support.

Operational note:
- the WhatsApp credentials now live on the retained OpenClaw state PVC
- moving to the dedicated number should be treated like a stateful credential migration, not a purely stateless config flip
- avoid overlapping rollouts where two pods try to come up against the same WhatsApp state at the same time

Acceptance criteria for the migration:
- OpenClaw no longer replies to its own messages
- a human user can message the assistant number and receive one reply per turn
- no self-echo loops appear in pod logs
- inbound and outbound message flow stays stable across a pod restart
- the assistant identity is clearly separate from any individual operator's personal account
