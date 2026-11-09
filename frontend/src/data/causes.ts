import type { LucideIcon } from "lucide-react";
import {
  Accessibility,
  Baby,
  Droplets,
  GraduationCap,
  HandHeart,
  HeartPulse,
  House,
  Landmark,
  LifeBuoy,
  PawPrint,
  Sprout,
  Trophy,
  Users,
  Wheat,
} from "lucide-react";

/**
 * What people give to on Veritas: causes run by organisations (charities, foundations,
 * public associations), never personal fundraisers.
 *
 * The backend files every project under one of eight categories
 * (backend/src/veritas/passport/models.py, `Category`). Causes are finer than that, so
 * each one names the category its projects carry; filtering the API by cause means
 * filtering by that category.
 */
export type ApiCategory =
  | "education"
  | "health"
  | "water"
  | "housing"
  | "environment"
  | "community"
  | "emergency"
  | "other";

export type CauseKey =
  | "education"
  | "health"
  | "water"
  | "housing"
  | "emergency"
  | "environment"
  | "community"
  | "children"
  | "elderly"
  | "disability"
  | "food"
  | "animals"
  | "culture"
  | "sport";

export type Cause = {
  key: CauseKey;
  label: string;
  /** One line under the tile and on the cause page. */
  blurb: string;
  icon: LucideIcon;
  category: ApiCategory;
  /** Header photo on the cause page (public/img). */
  photo: string;
};

export const CAUSES: Cause[] = [
  {
    key: "education",
    label: "Education",
    blurb: "Schools, kindergartens, libraries and the classrooms in them.",
    icon: GraduationCap,
    category: "education",
    photo: "/img/children-listening.jpg",
  },
  {
    key: "health",
    label: "Health",
    blurb: "Clinics, medical equipment and care that reaches remote villages.",
    icon: HeartPulse,
    category: "health",
    photo: "/img/elderly-care.jpg",
  },
  {
    key: "water",
    label: "Clean water",
    blurb: "Wells, pipes and sanitation, so taps run clean.",
    icon: Droplets,
    category: "water",
    photo: "/img/girl-water.jpg",
  },
  {
    key: "housing",
    label: "Housing",
    blurb: "Rebuilding homes and shelters after floods, fires and earthquakes.",
    icon: House,
    category: "housing",
    photo: "/img/builders-smiling.jpg",
  },
  {
    key: "emergency",
    label: "Emergency relief",
    blurb: "Fast help when disaster strikes: heating, shelter, supplies.",
    icon: LifeBuoy,
    category: "emergency",
    photo: "/img/food-relief.jpg",
  },
  {
    key: "environment",
    label: "Environment",
    blurb: "Trees, clean-ups, recycling and green spaces.",
    icon: Sprout,
    category: "environment",
    photo: "/img/planting.jpg",
  },
  {
    key: "community",
    label: "Community",
    blurb: "Bridges, community centres and the places neighbours share.",
    icon: Users,
    category: "community",
    photo: "/img/volunteers-cleanup.jpg",
  },
  {
    key: "children",
    label: "Children & youth",
    blurb: "Safe places to learn, play and grow up.",
    icon: Baby,
    category: "community",
    photo: "/img/children-listening.jpg",
  },
  {
    key: "elderly",
    label: "Elderly care",
    blurb: "Day centres, home care and company for older people.",
    icon: HandHeart,
    category: "health",
    photo: "/img/elderly-care.jpg",
  },
  {
    key: "disability",
    label: "Disability & inclusion",
    blurb: "Accessible buildings, equipment and inclusive play.",
    icon: Accessibility,
    category: "health",
    photo: "/img/community-shovels.jpg",
  },
  {
    key: "food",
    label: "Food security",
    blurb: "Food banks and parcels for families who need them.",
    icon: Wheat,
    category: "other",
    photo: "/img/food-relief.jpg",
  },
  {
    key: "animals",
    label: "Animal welfare",
    blurb: "Shelters, rescue and veterinary care for animals.",
    icon: PawPrint,
    category: "other",
    photo: "/img/dog-care.jpg",
  },
  {
    key: "culture",
    label: "Culture & heritage",
    blurb: "Restoring historic buildings and keeping traditions alive.",
    icon: Landmark,
    category: "community",
    photo: "/img/builder-frame.jpg",
  },
  {
    key: "sport",
    label: "Sport",
    blurb: "Pitches, gyms and teams for young people.",
    icon: Trophy,
    category: "community",
    photo: "/img/community-shovels.jpg",
  },
];

const BY_KEY = new Map(CAUSES.map((c) => [c.key, c]));

export function causeOf(key: string | undefined | null): Cause | undefined {
  return key ? BY_KEY.get(key as CauseKey) : undefined;
}
