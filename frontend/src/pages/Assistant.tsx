import { MessageCircle } from "lucide-react";
import { Page, PageHead } from "@/components/console/kit";
import { AssistantChat } from "@/components/assistant/AssistantChat";

export default function Assistant() {
  return (
    <Page>
      <PageHead
        eyebrow="Assistant"
        icon={MessageCircle}
        title="Ask Veritas"
        sub="Questions about how giving works, where your money waits, how the work is proven and how the blockchain keeps every step public."
      />
      <AssistantChat autoFocus />
    </Page>
  );
}
