import { Building2, FolderKanban, HandHeart, LayoutGrid, Map as MapIcon, MessageCircle, Receipt, Settings, ShieldCheck } from "lucide-react";
import type { ElementType } from "react";
import type { AccountType } from "@/contexts/AuthContext";

/** Every destination in the console, in rail order. One list feeds the rail, the mobile
 *  bar, its "More" sheet and the top bar's search, so a page added here appears in all
 *  four. */
export type Destination = {
  to: string;
  label: string;
  short?: string;
  icon: ElementType;
  tour?: string;
  /** Exact match only, rather than a path prefix. */
  end?: boolean;
  keywords?: string;
  /** Only for accounts that raise money for an organisation. */
  orgOnly?: boolean;
  /** A page of the public site, with the site's own frame rather than the console's. */
  publicPage?: boolean;
};

export const DESTINATIONS: Destination[] = [
  { to: "/dashboard", label: "Dashboard", short: "Home", icon: LayoutGrid, tour: "nav-dashboard", end: true, keywords: "home overview summary" },
  { to: "/donations", label: "My donations", short: "Giving", icon: Receipt, tour: "nav-donations", keywords: "receipts escrow released refunded pledges gifts history" },
  { to: "/donate", label: "Give", icon: HandHeart, tour: "nav-give", publicPage: true, keywords: "donate causes projects categories charity" },
  { to: "/map", label: "Donation map", short: "Map", icon: MapIcon, tour: "nav-map", publicPage: true, keywords: "regions where map azerbaijan" },
  { to: "/how-it-works", label: "How it works", short: "Trust", icon: ShieldCheck, publicPage: true, keywords: "trust security transparency safe blockchain escrow ai checks verification officer vote proof how" },
  { to: "/assistant", label: "Assistant", short: "Ask", icon: MessageCircle, keywords: "chat help questions ask ai bot support" },
  { to: "/organisation", label: "Organisation", short: "Org", icon: Building2, tour: "nav-org", end: true, orgOnly: true, keywords: "charity verification documents status voen" },
  { to: "/organisation/projects", label: "Projects", icon: FolderKanban, tour: "nav-projects", orgOnly: true, keywords: "fundraising milestones evidence publish" },
];

export const SETTINGS: Destination = {
  to: "/settings",
  label: "Settings",
  icon: Settings,
  keywords: "profile account sign-in google password email security",
};

export function destinationsFor(accountType: AccountType | null): Destination[] {
  return DESTINATIONS.filter((d) => !d.orgOnly || accountType === "organisation");
}

export const isLive = (pathname: string, d: Destination) =>
  d.end ? pathname === d.to : pathname === d.to || pathname.startsWith(d.to + "/");
