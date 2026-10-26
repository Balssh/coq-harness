using System;
using XRL;
using XRL.World;

namespace CoQMcpBridge
{
    [Serializable]
    public class BridgePart : IPart
    {
        public override bool WantEvent(int ID, int cascade)
        {
            return base.WantEvent(ID, cascade)
                || ID == EndTurnEvent.ID
                || ID == BeforeRenderEvent.ID
                || ID == BeginTakeActionEvent.ID;
        }

        public override bool HandleEvent(EndTurnEvent E)
        {
            Bridge.Tick(ParentObject);
            return base.HandleEvent(E);
        }

        public override bool HandleEvent(BeginTakeActionEvent E)
        {
            Bridge.TickAction(ParentObject);
            return base.HandleEvent(E);
        }

        public override bool HandleEvent(BeforeRenderEvent E)
        {
            Bridge.TickRender(ParentObject);
            return base.HandleEvent(E);
        }
    }

    [PlayerMutator]
    public class BridgeMutator : IPlayerMutator
    {
        public void mutate(GameObject player)
        {
            if (!player.HasPart<BridgePart>())
                player.AddPart(new BridgePart());
            Bridge.EnsureStarted();
        }
    }
}
