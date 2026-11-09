import type { CauseKey } from "./causes";
import type { RegionKey } from "./regions";
import type { Qapik } from "@/lib/money";

/**
 * SAMPLE DATA. Every organisation, contractor and project below is made up, so the web
 * app has something true-to-life to show before the public API serves real projects
 * (backend: GET /v1/projects). Pages that show it say so with a "Sample data" mark;
 * nothing here is presented as a real organisation or a real donation.
 *
 * The shapes follow the backend's: money is integer qəpik, a project is split into
 * milestones, each milestone's money waits in escrow until its evidence is checked and
 * approved, and only then is it paid to the contractor. A project's goal is the sum of
 * its milestone budgets and what it has raised is the sum of what each milestone holds,
 * so the two can never disagree.
 */
export const SAMPLE = true;

export type OrganisationKind = "Public union" | "Foundation" | "Charity";

export type Organisation = {
  id: string;
  name: string;
  kind: OrganisationKind;
  city: string;
  founded: number;
  /** When Veritas verified its registration, documents and bank account. */
  verifiedAt: string;
  about: string;
};

/**
 * Where a milestone stands. The money moves only forwards:
 * waiting → funding → funded → evidence → checked → approved → paid.
 * When a project stops, every milestone not paid yet is "stopped": what it held went back.
 */
export type MilestoneStatus =
  | "waiting" // later milestone, not collecting yet
  | "funding" // collecting donations
  | "funded" // fully funded, the work is under way
  | "evidence" // photos from the site are in, checks are running
  | "checked" // every check passed, waiting for the officer (and the donors' vote, if any)
  | "approved" // approved; the payment to the contractor is on its way
  | "paid" // released to the contractor
  | "stopped"; // the project stopped first: its money went back to the donors

export type Evidence = {
  photos: number;
  checksPassed: number;
  checksTotal: number;
  /** When the evidence bundle's hash was recorded on-chain. */
  anchoredAt?: string;
};

export type Milestone = {
  title: string;
  budget: Qapik;
  funded: Qapik;
  status: MilestoneStatus;
  due: string;
  evidence?: Evidence;
  paidAt?: string;
};

export type ProjectStatus = "live" | "completed" | "stopped";

export type Project = {
  id: string;
  title: string;
  summary: string;
  story: string[];
  cause: CauseKey;
  orgId: string;
  contractor: { name: string; trade: string };
  /** Its economic region, for a project in Azerbaijan; null for one abroad. */
  region: RegionKey | null;
  /** Where it is, when not Azerbaijan. */
  country?: string;
  place: string;
  lat: number;
  lng: number;
  photo: string;
  status: ProjectStatus;
  publishedAt: string;
  donors: number;
  /** Activity in the last 30 days, which the map shades by. */
  recent: { donations: number; raised: Qapik };
  milestones: Milestone[];
  updates: { date: string; text: string }[];
  /** A stopped project: when, why, and what went back to its donors. */
  stop?: { at: string; reason: string; refunded: Qapik; redirected: Qapik };
};

const m = (manat: number): Qapik => manat * 100;
const checked = (photos: number, anchoredAt: string): Evidence => ({ photos, checksPassed: 5, checksTotal: 5, anchoredAt });

export const ORGANISATIONS: Organisation[] = [
  { id: "first-steps", name: "First Steps Children's Fund", kind: "Foundation", city: "Bakı", founded: 2014, verifiedAt: "2026-05-12", about: "Schools, kindergartens and safe places to play, in towns the big programmes miss." },
  { id: "clean-springs", name: "Clean Springs Foundation", kind: "Foundation", city: "Ağdaş", founded: 2017, verifiedAt: "2026-05-30", about: "Wells, pipes and sanitation for villages and schools without running water." },
  { id: "warm-home", name: "Warm Home Initiative", kind: "Public union", city: "Sabirabad", founded: 2010, verifiedAt: "2026-04-21", about: "Rebuilds homes after floods and fires, with the families who live in them." },
  { id: "green-caspian", name: "Green Caspian Alliance", kind: "Public union", city: "Sumqayıt", founded: 2019, verifiedAt: "2026-06-03", about: "Trees, clean-ups and recycling along the coast and the rivers that feed it." },
  { id: "field-to-table", name: "Field to Table Food Bank", kind: "Charity", city: "Lənkəran", founded: 2016, verifiedAt: "2026-07-08", about: "Food parcels for families in need, bought from local farms where it can." },
  { id: "silver-years", name: "Silver Years Care Association", kind: "Public union", city: "Gəncə", founded: 2012, verifiedAt: "2026-05-19", about: "Day centres, home visits and company for older people living alone." },
  { id: "paw-shelter", name: "Paw & Shelter", kind: "Charity", city: "Bakı", founded: 2015, verifiedAt: "2026-06-14", about: "Rescues, treats and rehomes stray dogs and cats across Absheron." },
  { id: "open-doors", name: "Open Doors Inclusion Network", kind: "Public union", city: "Bakı", founded: 2013, verifiedAt: "2026-05-26", about: "Accessible places and equipment for children and adults with disabilities." },
  { id: "bridge-of-hope", name: "Bridge of Hope Community Fund", kind: "Foundation", city: "Bakı", founded: 2011, verifiedAt: "2026-04-30", about: "Libraries, bridges and community buildings that small places depend on." },
  { id: "healthy-valleys", name: "Healthy Valleys Medical Aid", kind: "Charity", city: "Lənkəran", founded: 2018, verifiedAt: "2026-06-22", about: "Brings doctors and medicine to mountain villages far from a clinic." },
  { id: "ready-hands", name: "Ready Hands Relief", kind: "Charity", city: "Qazax", founded: 2009, verifiedAt: "2026-07-15", about: "Emergency help within days of a disaster: heat, shelter and supplies." },
  { id: "young-champions", name: "Young Champions Sports Union", kind: "Public union", city: "Şamaxı", founded: 2020, verifiedAt: "2026-07-02", about: "Pitches, kit and coaching for young people outside the big cities." },
  { id: "heritage-trust", name: "Living Heritage Trust", kind: "Foundation", city: "Şuşa", founded: 2021, verifiedAt: "2026-06-09", about: "Restores historic buildings with the craftspeople who know how they were made." },
  { id: "kind-neighbours", name: "Kind Neighbours Refugee Aid", kind: "Public union", city: "Bakı", founded: 2022, verifiedAt: "2026-09-30", about: "Helps families who fled the war in Ukraine settle in Azerbaijan: homes, school places and winter clothes." },
];

export const PROJECTS: Project[] = [
  {
    id: "shaki-school-roof",
    title: "A new roof for School No. 3 in Şəki",
    summary: "Four hundred pupils have learned under a leaking roof for three winters. This replaces it before the next one.",
    story: [
      "School No. 3 teaches 410 children in two shifts. Its roof was last replaced in 1987, and every heavy rain now closes two classrooms on the top floor.",
      "The work is split into four milestones. Each one is paid to the builder only after photos from the roof prove it is done and Veritas's checks pass.",
    ],
    cause: "education",
    orgId: "first-steps",
    contractor: { name: "Qala Construction", trade: "Roofing and general building" },
    region: "shaki-zagatala",
    place: "Şəki",
    lat: 41.1975,
    lng: 47.1694,
    photo: "/img/builder-frame.jpg",
    status: "live",
    publishedAt: "2026-08-14",
    donors: 412,
    recent: { donations: 96, raised: m(9_840) },
    milestones: [
      { title: "Scaffolding and removing the old roof", budget: m(9_500), funded: m(9_500), status: "paid", due: "2026-09-15", evidence: checked(14, "2026-09-16"), paidAt: "2026-09-20" },
      { title: "New roof frame", budget: m(18_200), funded: m(18_200), status: "checked", due: "2026-10-31", evidence: checked(19, "2026-11-02") },
      { title: "Roofing sheets and gutters", budget: m(14_600), funded: m(8_720), status: "funding", due: "2026-12-10" },
      { title: "Ceilings and paint", budget: m(5_700), funded: 0, status: "waiting", due: "2027-01-20" },
    ],
    updates: [
      { date: "2026-11-02", text: "Photos of the finished roof frame passed all five checks and are waiting for the officer's review." },
      { date: "2026-09-20", text: "₼9,500 released to Qala Construction for the scaffolding and removal of the old roof." },
    ],
  },
  {
    id: "agdash-water",
    title: "Clean drinking water for three villages near Ağdaş",
    summary: "A solar-powered well and 6 km of pipe, so 2,100 people stop carrying water from the canal.",
    story: [
      "Three villages north of Ağdaş share one standpipe that runs dry most of the summer. Families fetch water from an irrigation canal and boil it.",
      "A new well with a solar pump feeds a storage tank, and pipes take the water to every street. Each stage is paid only once the site photos prove it.",
    ],
    cause: "water",
    orgId: "clean-springs",
    contractor: { name: "Kür Water Engineering", trade: "Wells, pumps and pipelines" },
    region: "central-aran",
    place: "Ağdaş",
    lat: 40.6467,
    lng: 47.4766,
    photo: "/img/girl-water.jpg",
    status: "live",
    publishedAt: "2026-07-30",
    donors: 1_038,
    recent: { donations: 214, raised: m(21_350) },
    milestones: [
      { title: "Survey and permits", budget: m(6_000), funded: m(6_000), status: "paid", due: "2026-08-20", evidence: checked(6, "2026-08-21"), paidAt: "2026-08-25" },
      { title: "Drill and line the well", budget: m(38_000), funded: m(38_000), status: "paid", due: "2026-09-30", evidence: checked(24, "2026-10-01"), paidAt: "2026-10-06" },
      { title: "Pump station and solar power", budget: m(42_000), funded: m(42_000), status: "evidence", due: "2026-11-15", evidence: { photos: 22, checksPassed: 3, checksTotal: 5 } },
      { title: "Pipes to the three villages", budget: m(54_000), funded: m(21_600), status: "funding", due: "2027-02-28" },
    ],
    updates: [
      { date: "2026-11-06", text: "22 photos of the pump station arrived from the site; the checks are running." },
      { date: "2026-10-06", text: "₼38,000 released to Kür Water Engineering for the finished well." },
    ],
  },
  {
    id: "sabirabad-homes",
    title: "Rebuilding 12 flood-damaged homes in Sabirabad",
    summary: "Twelve families lost their homes when the Kür broke its banks. The walls are up; the roofs are next.",
    story: [
      "The spring flood destroyed 12 houses in one street of Sabirabad. The families have spent the summer with relatives.",
      "Warm Home Initiative is rebuilding all twelve to the same plan, with raised floors so the next flood stays outside.",
    ],
    cause: "housing",
    orgId: "warm-home",
    contractor: { name: "Araz Construction", trade: "Residential building" },
    region: "mil-mughan",
    place: "Sabirabad",
    lat: 40.0129,
    lng: 48.4778,
    photo: "/img/builders-smiling.jpg",
    status: "live",
    publishedAt: "2026-06-02",
    donors: 2_904,
    recent: { donations: 388, raised: m(46_200) },
    milestones: [
      { title: "Clearing the plots and new foundations", budget: m(48_000), funded: m(48_000), status: "paid", due: "2026-07-15", evidence: checked(36, "2026-07-16"), paidAt: "2026-07-22" },
      { title: "Walls for 12 homes", budget: m(96_000), funded: m(96_000), status: "paid", due: "2026-09-10", evidence: checked(48, "2026-09-12"), paidAt: "2026-09-18" },
      { title: "Roofs", budget: m(72_000), funded: m(72_000), status: "approved", due: "2026-10-31", evidence: checked(41, "2026-10-29") },
      { title: "Windows, doors and wiring", budget: m(64_000), funded: m(51_300), status: "funding", due: "2026-12-15" },
      { title: "Handing the keys to the families", budget: m(20_000), funded: 0, status: "waiting", due: "2027-01-31" },
    ],
    updates: [
      { date: "2026-11-04", text: "The roofs were approved. ₼72,000 is on its way to Araz Construction." },
      { date: "2026-09-18", text: "All twelve sets of walls are finished; ₼96,000 released." },
    ],
  },
  {
    id: "absheron-trees",
    title: "20,000 trees along the Absheron coast",
    summary: "A green belt between Sumqayıt and the sea, with drip irrigation so the saplings survive their first summer.",
    story: [
      "The coast north of Sumqayıt is bare sand and dust. Volunteers will plant 20,000 native trees in two seasons.",
      "The irrigation lines go in first; each planting season is paid only after photos of the planted rows pass the checks.",
    ],
    cause: "environment",
    orgId: "green-caspian",
    contractor: { name: "Yaşıl Bağ Landscaping", trade: "Planting and irrigation" },
    region: "absheron-khizi",
    place: "Sumqayıt",
    lat: 40.605,
    lng: 49.63,
    photo: "/img/planting.jpg",
    status: "live",
    publishedAt: "2026-09-21",
    donors: 1_560,
    recent: { donations: 602, raised: m(18_900) },
    milestones: [
      { title: "Saplings and irrigation lines", budget: m(26_000), funded: m(26_000), status: "checked", due: "2026-11-01", evidence: checked(31, "2026-11-03") },
      { title: "Planting the first 10,000 trees", budget: m(22_000), funded: m(9_400), status: "funding", due: "2026-12-20" },
      { title: "10,000 more and the first summer's watering", budget: m(24_000), funded: 0, status: "waiting", due: "2027-04-30" },
    ],
    updates: [{ date: "2026-11-03", text: "The irrigation lines are in and their photos passed every check." }],
  },
  {
    id: "lankaran-food",
    title: "Winter food parcels for 600 families in Lənkəran",
    summary: "Flour, oil, rice, lentils and tea for the coldest months, bought from farms in the region.",
    story: [
      "Six hundred families on the food bank's list will receive a parcel each month from December to February.",
      "Each delivery of 300 parcels is photographed at the warehouse and on the way out, and paid to the supplier only then.",
    ],
    cause: "food",
    orgId: "field-to-table",
    contractor: { name: "Lənkəran Wholesale Supply", trade: "Food wholesale" },
    region: "lankaran-astara",
    place: "Lənkəran",
    lat: 38.7529,
    lng: 48.8475,
    photo: "/img/food-relief.jpg",
    status: "live",
    publishedAt: "2026-10-12",
    donors: 731,
    recent: { donations: 512, raised: m(15_260) },
    milestones: [
      { title: "The first 300 parcels", budget: m(15_000), funded: m(15_000), status: "funded", due: "2026-12-05" },
      { title: "The second 300 parcels", budget: m(15_000), funded: m(3_260), status: "funding", due: "2027-01-05" },
    ],
    updates: [{ date: "2026-11-01", text: "The first 300 parcels are fully funded. Packing starts in late November." }],
  },
  {
    id: "ganja-day-centre",
    title: "A day centre for older people in Gəncə",
    summary: "A warm place to spend the day, eat a hot lunch and see a nurse, for 60 people who live alone.",
    story: [
      "A disused kindergarten building is being turned into a day centre with a kitchen, a lounge and a nurse's room.",
      "The renovation is done; ramps and accessible bathrooms come next, then furniture and the first year's staff.",
    ],
    cause: "elderly",
    orgId: "silver-years",
    contractor: { name: "Gəncə Build", trade: "Renovation" },
    region: "ganja-dashkasan",
    place: "Gəncə",
    lat: 40.6828,
    lng: 46.3606,
    photo: "/img/elderly-care.jpg",
    status: "live",
    publishedAt: "2026-08-28",
    donors: 654,
    recent: { donations: 140, raised: m(12_480) },
    milestones: [
      { title: "Renovating the building", budget: m(34_000), funded: m(34_000), status: "paid", due: "2026-10-01", evidence: checked(27, "2026-10-02"), paidAt: "2026-10-08" },
      { title: "Accessible bathrooms and ramps", budget: m(16_500), funded: m(16_500), status: "checked", due: "2026-11-10", evidence: checked(17, "2026-11-05") },
      { title: "Furniture and the first year's care staff", budget: m(21_500), funded: m(6_980), status: "funding", due: "2027-01-15" },
    ],
    updates: [{ date: "2026-11-05", text: "Photos of the ramps and bathrooms passed all five checks." }],
  },
  {
    id: "baku-shelter",
    title: "Room for 80 more dogs at a Bakı animal shelter",
    summary: "New kennels, a vet room and winter heating for a shelter that turns dogs away every week.",
    story: [
      "The shelter in Binəqədi houses 140 dogs and has a waiting list. New kennels add room for 80 more.",
      "A small vet room with an isolation ward means sick animals can be treated on site instead of driven across the city.",
    ],
    cause: "animals",
    orgId: "paw-shelter",
    contractor: { name: "Abşeron Steel Works", trade: "Steel structures and fencing" },
    region: "baku",
    place: "Bakı, Binəqədi",
    lat: 40.46,
    lng: 49.83,
    photo: "/img/dog-care.jpg",
    status: "live",
    publishedAt: "2026-09-05",
    donors: 2_210,
    recent: { donations: 690, raised: m(16_840) },
    milestones: [
      { title: "Kennels and fencing", budget: m(21_000), funded: m(21_000), status: "paid", due: "2026-10-10", evidence: checked(18, "2026-10-11"), paidAt: "2026-10-15" },
      { title: "Vet room and isolation ward", budget: m(17_000), funded: m(17_000), status: "evidence", due: "2026-11-20", evidence: { photos: 15, checksPassed: 4, checksTotal: 5 } },
      { title: "Heating for the winter", budget: m(9_000), funded: m(4_120), status: "funding", due: "2026-12-15" },
    ],
    updates: [{ date: "2026-11-07", text: "Photos of the vet room are in; four of the five checks have passed so far." }],
  },
  {
    id: "mingachevir-playground",
    title: "An accessible playground in Mingəçevir",
    summary: "Swings, a carousel and sensory panels that children in wheelchairs can use with everyone else.",
    story: [
      "The town has no playground a child in a wheelchair can use. This one is built on the riverside park, on a soft, level surface.",
    ],
    cause: "disability",
    orgId: "open-doors",
    contractor: { name: "Mingəçevir Park Works", trade: "Landscaping and play equipment" },
    region: "central-aran",
    place: "Mingəçevir",
    lat: 40.764,
    lng: 47.0595,
    photo: "/img/community-shovels.jpg",
    status: "live",
    publishedAt: "2026-10-01",
    donors: 388,
    recent: { donations: 201, raised: m(7_830) },
    milestones: [
      { title: "Ground works and the soft surface", budget: m(14_000), funded: m(14_000), status: "funded", due: "2026-12-01" },
      { title: "Accessible swings, carousel and sensory panels", budget: m(19_000), funded: m(2_830), status: "funding", due: "2027-03-01" },
    ],
    updates: [{ date: "2026-10-28", text: "The ground works are fully funded and start next week." }],
  },
  {
    id: "guba-recycling",
    title: "Clean-up days and recycling points in Quba",
    summary: "Finished: the riverbank is clear and 40 recycling points serve the town.",
    story: [
      "Volunteers cleared 6 km of the Qudyalçay riverbank, and the town now has 40 recycling points, emptied every week.",
    ],
    cause: "environment",
    orgId: "green-caspian",
    contractor: { name: "Quba Municipal Services", trade: "Waste collection" },
    region: "guba-khachmaz",
    place: "Quba",
    lat: 41.3611,
    lng: 48.5126,
    photo: "/img/volunteers-cleanup.jpg",
    status: "completed",
    publishedAt: "2026-04-18",
    donors: 846,
    recent: { donations: 12, raised: m(310) },
    milestones: [
      { title: "Riverbank clean-up", budget: m(6_500), funded: m(6_500), status: "paid", due: "2026-05-20", evidence: checked(40, "2026-05-21"), paidAt: "2026-05-26" },
      { title: "40 recycling points", budget: m(12_500), funded: m(12_500), status: "paid", due: "2026-07-01", evidence: checked(44, "2026-07-02"), paidAt: "2026-07-07" },
    ],
    updates: [{ date: "2026-07-07", text: "Project complete. Every manat raised has been paid out against checked evidence." }],
  },
  {
    id: "nakhchivan-library",
    title: "A library and reading room for a school in Naxçıvan",
    summary: "Shelves, reading tables and 4,000 books in Azerbaijani, Russian and English.",
    story: ["The school's library is one bookcase in a corridor. A classroom becomes a reading room with books for every age."],
    cause: "education",
    orgId: "bridge-of-hope",
    contractor: { name: "Naxçıvan Interiors", trade: "Furniture and fit-out" },
    region: "nakhchivan",
    place: "Naxçıvan",
    lat: 39.2089,
    lng: 45.4122,
    photo: "/img/children-listening.jpg",
    status: "live",
    publishedAt: "2026-09-30",
    donors: 433,
    recent: { donations: 119, raised: m(5_150) },
    milestones: [
      { title: "Shelving and furniture", budget: m(9_000), funded: m(9_000), status: "funded", due: "2026-11-30" },
      { title: "4,000 books", budget: m(12_000), funded: m(5_450), status: "funding", due: "2027-01-31" },
    ],
    updates: [{ date: "2026-10-22", text: "The furniture is fully funded and on order." }],
  },
  {
    id: "fuzuli-kindergarten",
    title: "Furnishing a new kindergarten in Füzuli",
    summary: "Beds, tables, a kitchen and a playground for a kindergarten opening to 120 children.",
    story: ["The building is finished; it stands empty until it is furnished. This fits out six groups, a kitchen and the yard."],
    cause: "children",
    orgId: "first-steps",
    contractor: { name: "Qala Construction", trade: "Fit-out and playgrounds" },
    region: "karabakh",
    place: "Füzuli",
    lat: 39.6003,
    lng: 47.1431,
    photo: "/img/builder-frame.jpg",
    status: "live",
    publishedAt: "2026-10-20",
    donors: 297,
    recent: { donations: 297, raised: m(11_640) },
    milestones: [
      { title: "Furniture for six groups", budget: m(18_000), funded: m(11_640), status: "funding", due: "2026-12-20" },
      { title: "Playground", budget: m(15_000), funded: 0, status: "waiting", due: "2027-03-15" },
      { title: "Kitchen equipment", budget: m(9_000), funded: 0, status: "waiting", due: "2027-04-15" },
    ],
    updates: [{ date: "2026-10-20", text: "Published after Veritas checked the plan and the contractor." }],
  },
  {
    id: "lerik-clinic",
    title: "A mobile clinic for mountain villages around Lerik",
    summary: "A clinic on wheels that visits 18 villages a month, with a doctor, a nurse and a pharmacy.",
    story: ["Some villages are three hours from the nearest clinic. The van brings check-ups, vaccinations and medicine to them."],
    cause: "health",
    orgId: "healthy-valleys",
    contractor: { name: "Medtex Supply", trade: "Medical vehicles and equipment" },
    region: "lankaran-astara",
    place: "Lerik",
    lat: 38.7739,
    lng: 48.415,
    photo: "/img/elderly-care.jpg",
    status: "live",
    publishedAt: "2026-08-05",
    donors: 1_402,
    recent: { donations: 180, raised: m(9_450) },
    milestones: [
      { title: "The vehicle, fitted as a clinic", budget: m(64_000), funded: m(64_000), status: "approved", due: "2026-10-30", evidence: checked(21, "2026-10-28") },
      { title: "Equipment and medicine for the first year", budget: m(36_000), funded: m(12_900), status: "funding", due: "2027-01-30" },
    ],
    updates: [{ date: "2026-11-03", text: "The fitted vehicle was approved; payment to Medtex Supply is on its way." }],
  },
  {
    id: "gazakh-heating",
    title: "Emergency heating for families after the storm in Qazax",
    summary: "Stoves and fuel for 150 homes now, roof repairs for 40 of them before the snow.",
    story: ["October's storm tore roofs off across three villages. Families are heating one room and living in it."],
    cause: "emergency",
    orgId: "ready-hands",
    contractor: { name: "Tovuz Energy Services", trade: "Heating and roofing" },
    region: "gazakh-tovuz",
    place: "Qazax",
    lat: 41.0925,
    lng: 45.3656,
    photo: "/img/food-relief.jpg",
    status: "live",
    publishedAt: "2026-10-24",
    donors: 1_120,
    recent: { donations: 540, raised: m(24_100) },
    milestones: [
      { title: "Stoves and fuel for 150 homes", budget: m(22_500), funded: m(22_500), status: "evidence", due: "2026-11-10", evidence: { photos: 64, checksPassed: 2, checksTotal: 5 } },
      { title: "Roof repairs for 40 homes", budget: m(31_500), funded: m(14_700), status: "funding", due: "2026-12-15" },
    ],
    updates: [{ date: "2026-11-07", text: "Stoves delivered to all 150 homes; the delivery photos are being checked." }],
  },
  {
    id: "shamakhi-pitch",
    title: "A football pitch for young people in Şamaxı",
    summary: "An all-weather pitch with lights, open to every school and club in the district.",
    story: ["Teams train on a dirt field that turns to mud from October to April. This builds a pitch they can use all year."],
    cause: "sport",
    orgId: "young-champions",
    contractor: { name: "Şirvan Sport Build", trade: "Sports surfaces" },
    region: "mountainous-shirvan",
    place: "Şamaxı",
    lat: 40.6314,
    lng: 48.6414,
    photo: "/img/community-shovels.jpg",
    status: "live",
    publishedAt: "2026-07-18",
    donors: 903,
    recent: { donations: 161, raised: m(6_220) },
    milestones: [
      { title: "Drainage and the base", budget: m(21_000), funded: m(21_000), status: "paid", due: "2026-09-15", evidence: checked(16, "2026-09-16"), paidAt: "2026-09-21" },
      { title: "Artificial turf and goals", budget: m(33_000), funded: m(18_550), status: "funding", due: "2026-12-01" },
      { title: "Floodlights", budget: m(12_000), funded: 0, status: "waiting", due: "2027-02-01" },
    ],
    updates: [{ date: "2026-09-21", text: "₼21,000 released for the drainage and base." }],
  },
  {
    id: "shusha-caravanserai",
    title: "Restoring the roof of a historic caravanserai in Şuşa",
    summary: "A timber and clay-tile roof, made the way the original was, to keep the 18th-century walls dry.",
    story: ["The caravanserai's walls stand but its roof is gone. Restorers are rebuilding it with traditional timber joints and tiles."],
    cause: "culture",
    orgId: "heritage-trust",
    contractor: { name: "Restoration Guild", trade: "Heritage restoration" },
    region: "karabakh",
    place: "Şuşa",
    lat: 39.7583,
    lng: 46.7486,
    photo: "/img/builder-frame.jpg",
    status: "live",
    publishedAt: "2026-06-27",
    donors: 1_788,
    recent: { donations: 233, raised: m(8_940) },
    milestones: [
      { title: "Structural survey", budget: m(8_000), funded: m(8_000), status: "paid", due: "2026-07-31", evidence: checked(12, "2026-08-01"), paidAt: "2026-08-06" },
      { title: "Timber roof structure", budget: m(46_000), funded: m(46_000), status: "checked", due: "2026-10-31", evidence: checked(33, "2026-11-04") },
      { title: "Stone and clay tiles", budget: m(38_000), funded: m(9_050), status: "funding", due: "2027-03-31" },
    ],
    updates: [{ date: "2026-11-04", text: "The timber structure is finished and its photos passed every check." }],
  },
  {
    id: "salyan-school-water",
    title: "Running water and toilets for a school in Salyan",
    summary: "A water tank, pipes and a new toilet block for 260 pupils who now use an outdoor latrine.",
    story: ["The school has no running water. A tank on the roof and a new toilet block change that."],
    cause: "water",
    orgId: "clean-springs",
    contractor: { name: "Kür Water Engineering", trade: "Wells, pumps and pipelines" },
    region: "shirvan-salyan",
    place: "Salyan",
    lat: 39.5955,
    lng: 48.9762,
    photo: "/img/girl-water.jpg",
    status: "live",
    publishedAt: "2026-09-12",
    donors: 511,
    recent: { donations: 176, raised: m(5_960) },
    milestones: [
      { title: "Water tank and pipes", budget: m(13_000), funded: m(13_000), status: "funded", due: "2026-11-30" },
      { title: "Toilet block", budget: m(17_000), funded: m(4_880), status: "funding", due: "2027-02-15" },
    ],
    updates: [{ date: "2026-10-30", text: "The tank and pipes are fully funded; work starts on 16 November." }],
  },
  {
    id: "lachin-bridge",
    title: "Rebuilding a footbridge for a village near Laçın",
    summary: "A steel footbridge so children can cross the river to school when it floods.",
    story: ["When the river rises, the village is cut off from the school and the road. The new bridge stands above the flood line."],
    cause: "community",
    orgId: "bridge-of-hope",
    contractor: { name: "Araz Construction", trade: "Bridges and civil works" },
    region: "east-zangezur",
    place: "Laçın",
    lat: 39.6406,
    lng: 46.5464,
    photo: "/img/builders-smiling.jpg",
    status: "live",
    publishedAt: "2026-08-22",
    donors: 620,
    recent: { donations: 148, raised: m(7_410) },
    milestones: [
      { title: "Foundations on both banks", budget: m(24_000), funded: m(24_000), status: "evidence", due: "2026-11-05", evidence: { photos: 20, checksPassed: 4, checksTotal: 5 } },
      { title: "Steel deck and railings", budget: m(29_000), funded: m(7_310), status: "funding", due: "2027-01-31" },
    ],
    updates: [{ date: "2026-11-06", text: "Photos of both foundations are in and being checked." }],
  },
  {
    id: "khachmaz-school-heating",
    title: "Warm classrooms for four schools in Xaçmaz",
    summary: "New boilers for four village schools whose heating failed last winter.",
    story: ["Last January four schools sent children home for a week because the boilers failed. Two are replaced; two to go."],
    cause: "education",
    orgId: "first-steps",
    contractor: { name: "Xəzər Heating", trade: "Heating systems" },
    region: "guba-khachmaz",
    place: "Xaçmaz",
    lat: 41.4635,
    lng: 48.806,
    photo: "/img/children-listening.jpg",
    status: "live",
    publishedAt: "2026-08-09",
    donors: 744,
    recent: { donations: 205, raised: m(8_120) },
    milestones: [
      { title: "Boilers for the first two schools", budget: m(19_000), funded: m(19_000), status: "paid", due: "2026-10-15", evidence: checked(14, "2026-10-16"), paidAt: "2026-10-21" },
      { title: "Boilers for the other two", budget: m(19_000), funded: m(12_260), status: "funding", due: "2026-12-15" },
    ],
    updates: [{ date: "2026-10-21", text: "Two schools are warm again; ₼19,000 released to Xəzər Heating." }],
  },
  {
    id: "baku-rehab",
    title: "Rehabilitation equipment for a children's centre in Bakı",
    summary: "Therapy equipment and a sensory room for 90 children with cerebral palsy and autism.",
    story: ["Families wait months for therapy sessions because the centre shares two pieces of equipment. This triples what it has."],
    cause: "disability",
    orgId: "open-doors",
    contractor: { name: "Medtex Supply", trade: "Medical and therapy equipment" },
    region: "baku",
    place: "Bakı, Nərimanov",
    lat: 40.403,
    lng: 49.873,
    photo: "/img/community-shovels.jpg",
    status: "live",
    publishedAt: "2026-09-02",
    donors: 1_302,
    recent: { donations: 388, raised: m(14_530) },
    milestones: [
      { title: "Therapy equipment", budget: m(28_000), funded: m(28_000), status: "approved", due: "2026-10-25", evidence: checked(11, "2026-10-27") },
      { title: "Sensory room", budget: m(14_000), funded: m(6_740), status: "funding", due: "2026-12-20" },
    ],
    updates: [{ date: "2026-11-01", text: "The equipment was approved; payment is on its way to Medtex Supply." }],
  },
  {
    id: "kharkiv-hospital-power",
    title: "Generators for a children's hospital in Kharkiv",
    summary: "Power cuts stop incubators and operating theatres. Two generators and a winter of fuel keep the hospital running through them.",
    story: [
      "Since the war began, the children's hospital in Kharkiv has lost mains power for hours at a time. Its old generator cannot carry intensive care and the operating theatres together.",
      "Ready Hands Relief buys two generators in Azerbaijan, drives them to Kharkiv with its partner there and has them installed. Each step is paid only when photos from the hospital pass the same checks as a project at home.",
    ],
    cause: "emergency",
    orgId: "ready-hands",
    contractor: { name: "Energoservis Kharkiv", trade: "Generators and electrical installation" },
    region: null,
    country: "Ukraine",
    place: "Kharkiv",
    lat: 49.9935,
    lng: 36.2304,
    photo: "/img/food-relief.jpg",
    status: "live",
    publishedAt: "2026-09-18",
    donors: 1_964,
    recent: { donations: 402, raised: m(31_200) },
    milestones: [
      { title: "Buy two 150 kW generators", budget: m(48_000), funded: m(48_000), status: "paid", due: "2026-10-05", evidence: checked(11, "2026-10-06"), paidAt: "2026-10-09" },
      { title: "Transport to Kharkiv", budget: m(9_500), funded: m(9_500), status: "paid", due: "2026-10-20", evidence: checked(16, "2026-10-22"), paidAt: "2026-10-24" },
      { title: "Installation and switchover", budget: m(14_000), funded: m(14_000), status: "evidence", due: "2026-11-12", evidence: { photos: 27, checksPassed: 4, checksTotal: 5 } },
      { title: "Fuel for the winter", budget: m(22_000), funded: m(9_350), status: "funding", due: "2027-01-15" },
    ],
    updates: [
      { date: "2026-11-07", text: "27 photos from the switch room arrived; four of the five checks have passed." },
      { date: "2026-10-24", text: "₼9,500 released for transport: both generators reached the hospital." },
    ],
  },
  {
    id: "baku-ukrainian-families",
    title: "A warm winter for Ukrainian families in Bakı",
    summary: "Winter coats, boots and school bags for 160 children whose families fled the war in Ukraine.",
    story: [
      "About sixty Ukrainian families who left the war live in rented flats around Bakı. Many arrived in summer clothes, and their children start the winter without coats or boots.",
      "Kind Neighbours buys the clothes from Bakı shops in the sizes the families give, and hands them out at the children's schools. Each delivery is paid only once photos of the handover pass Veritas's checks.",
    ],
    cause: "children",
    orgId: "kind-neighbours",
    contractor: { name: "Xəzər Textile Wholesale", trade: "Clothing and school supplies" },
    region: "baku",
    place: "Bakı",
    lat: 40.3953,
    lng: 49.8822,
    photo: "/img/children-listening.jpg",
    status: "live",
    publishedAt: "2026-10-28",
    donors: 286,
    recent: { donations: 241, raised: m(7_420) },
    milestones: [
      { title: "Winter coats and boots", budget: m(14_400), funded: m(7_420), status: "funding", due: "2026-12-01" },
      { title: "School bags and supplies", budget: m(4_800), funded: 0, status: "waiting", due: "2027-01-10" },
    ],
    updates: [{ date: "2026-10-28", text: "Published, with the sizes collected from all sixty families." }],
  },
  {
    id: "aghdam-returning-homes",
    title: "Homes for 20 families returning to Ağdam",
    summary: "Twenty families are moving back to Ağdam after almost thirty years away. This builds the houses they come home to.",
    story: [
      "Ağdam has been rebuilt street by street since 2021. Twenty families who left in 1993 have land in the new town and are waiting for homes on it.",
      "Warm Home Initiative builds all twenty to one plan with a local builder. The foundations are paid; the walls and roofs passed every check and wait for the officer and the donors' vote.",
    ],
    cause: "housing",
    orgId: "warm-home",
    contractor: { name: "Yeni Ev Tikinti", trade: "Housing construction" },
    region: "karabakh",
    place: "Ağdam",
    lat: 39.9911,
    lng: 46.9297,
    photo: "/img/builders-smiling.jpg",
    status: "live",
    publishedAt: "2026-06-30",
    donors: 2_318,
    recent: { donations: 188, raised: m(24_600) },
    milestones: [
      { title: "Foundations for 20 houses", budget: m(64_000), funded: m(64_000), status: "paid", due: "2026-08-31", evidence: checked(48, "2026-09-02"), paidAt: "2026-09-06" },
      { title: "Walls and roofs", budget: m(126_000), funded: m(126_000), status: "checked", due: "2026-11-01", evidence: checked(96, "2026-11-04") },
      { title: "Windows, doors and wiring", budget: m(58_000), funded: m(18_300), status: "funding", due: "2027-01-31" },
      { title: "Handing over the keys", budget: m(12_000), funded: 0, status: "waiting", due: "2027-03-15" },
    ],
    updates: [
      { date: "2026-11-04", text: "96 photos of the finished walls and roofs passed every check. The officer reviews them next; then this milestone's donors have 72 hours to vote." },
      { date: "2026-09-06", text: "₼64,000 released to Yeni Ev Tikinti for the foundations." },
    ],
  },
  {
    id: "ganja-school-ramps",
    title: "Ramps and lifts for eight schools in Gəncə",
    summary: "Eight schools a wheelchair cannot get into. This fits ramps, rails and a stair lift in each.",
    story: [
      "In Gəncə, 31 children who use wheelchairs are taught at home because their schools have steps at every door.",
      "Open Doors fits ramps and handrails in eight schools, four at a time, then a stair lift in each. The first four are done and approved; the payment is on its way to the builder.",
    ],
    cause: "disability",
    orgId: "open-doors",
    contractor: { name: "Access Build Gəncə", trade: "Accessibility works" },
    region: "ganja-dashkasan",
    place: "Gəncə",
    lat: 40.6828,
    lng: 46.3606,
    photo: "/img/elderly-care.jpg",
    status: "live",
    publishedAt: "2026-07-22",
    donors: 873,
    recent: { donations: 133, raised: m(8_960) },
    milestones: [
      { title: "Ramps and rails in four schools", budget: m(28_000), funded: m(28_000), status: "approved", due: "2026-10-31", evidence: checked(40, "2026-11-01") },
      { title: "Ramps and rails in four more", budget: m(28_000), funded: m(11_400), status: "funding", due: "2027-02-28" },
      { title: "Stair lifts in all eight", budget: m(36_000), funded: 0, status: "waiting", due: "2027-05-31" },
    ],
    updates: [{ date: "2026-11-06", text: "Approved by the officer: ₼28,000 is on its way to Access Build Gəncə for the first four schools." }],
  },
  {
    id: "irpin-school-windows",
    title: "New windows for a school in Irpin",
    summary: "The shattered windows of a primary school in Irpin, replaced before the children came back to class.",
    story: [
      "The school lost most of its windows in 2022, when the fighting reached Irpin. For two winters the frames were boarded up and lessons moved to the basement.",
      "First Steps paid a local glazier in three stages, each released only when photos from the school passed Veritas's checks. All 214 windows are in.",
    ],
    cause: "education",
    orgId: "first-steps",
    contractor: { name: "Irpin Glass Works", trade: "Glazing" },
    region: null,
    country: "Ukraine",
    place: "Irpin",
    lat: 50.5218,
    lng: 30.2505,
    photo: "/img/volunteers-cleanup.jpg",
    status: "completed",
    publishedAt: "2026-04-15",
    donors: 1_427,
    recent: { donations: 12, raised: m(380) },
    milestones: [
      { title: "Ground floor windows", budget: m(16_800), funded: m(16_800), status: "paid", due: "2026-05-31", evidence: checked(22, "2026-06-02"), paidAt: "2026-06-05" },
      { title: "First floor windows", budget: m(18_400), funded: m(18_400), status: "paid", due: "2026-07-15", evidence: checked(25, "2026-07-17"), paidAt: "2026-07-21" },
      { title: "Gym and stairwell", budget: m(9_600), funded: m(9_600), status: "paid", due: "2026-08-25", evidence: checked(14, "2026-08-27"), paidAt: "2026-08-29" },
    ],
    updates: [
      { date: "2026-08-29", text: "Complete: ₼9,600 released for the gym and stairwell, the last of the windows." },
      { date: "2026-07-21", text: "₼18,400 released for the first floor." },
    ],
  },
  {
    id: "zaqatala-footbridge",
    title: "A footbridge over the Talaçay in Zaqatala",
    summary: "Stopped: the river authority refused the permit. Each donor chose a refund or moved their money to another bridge.",
    story: [
      "Children from two villages cross the Talaçay on stepping stones to reach school, and the river floods every spring.",
      "After the survey, the river authority refused the permit for the planned site. Bridge of Hope stopped the project: the survey was paid, and the rest went back to the donors, or to the Laçın footbridge for those who chose to move it.",
    ],
    cause: "community",
    orgId: "bridge-of-hope",
    contractor: { name: "Talaçay Engineering", trade: "Bridges and river works" },
    region: "shaki-zagatala",
    place: "Zaqatala",
    lat: 41.6314,
    lng: 46.6433,
    photo: "/img/community-shovels.jpg",
    status: "stopped",
    publishedAt: "2026-03-10",
    donors: 654,
    recent: { donations: 0, raised: 0 },
    stop: { at: "2026-07-02", reason: "The river authority refused the permit for the planned site.", refunded: m(13_900), redirected: m(5_100) },
    milestones: [
      { title: "Survey and design", budget: m(4_200), funded: m(4_200), status: "paid", due: "2026-04-30", evidence: checked(9, "2026-05-02"), paidAt: "2026-05-06" },
      { title: "Foundations on both banks", budget: m(19_000), funded: m(19_000), status: "stopped", due: "2026-07-31" },
      { title: "Steel deck and railings", budget: m(26_000), funded: 0, status: "stopped", due: "2026-09-30" },
    ],
    updates: [
      { date: "2026-07-09", text: "Stopped. ₼13,900 refunded to donors' cards, and ₼5,100 moved to the Laçın footbridge by the donors who chose it." },
      { date: "2026-05-06", text: "₼4,200 released to Talaçay Engineering for the survey and design." },
    ],
  },
  {
    // The finished project whose proof is all on show: every site photo, document and vote
    // (data/sample-proof.ts has its photos and documents).
    id: "ganja-school-7",
    title: "A warm, dry school for 380 pupils in Gəncə",
    summary: "School No. 7 had a leaking roof, broken windows and cold classrooms. Every stage is finished, proven and paid: open any milestone to see its photos, its documents and its vote.",
    story: [
      "For years the top floor of School No. 7 flooded whenever it rained, a third of its windows were cracked or boarded up, and two wings had no working heating, so lessons were squeezed into the warm rooms.",
      "First Steps split the work into four milestones with Kəpəz Construction. Each was paid only after the photos from the site, the invoice and the e-kassa receipt passed every check, the officer approved and the donors voted yes.",
    ],
    cause: "education",
    orgId: "first-steps",
    contractor: { name: "Kəpəz Construction", trade: "Roofs, windows and heating" },
    region: "ganja-dashkasan",
    place: "Gəncə",
    lat: 40.6828,
    lng: 46.3606,
    photo: "/img/proof/ganja-school/m4-classroom.jpg",
    status: "completed",
    publishedAt: "2026-04-06",
    donors: 538,
    recent: { donations: 0, raised: 0 },
    milestones: [
      { title: "Scaffolding up and the old roof off", budget: m(8_600), funded: m(8_600), status: "paid", due: "2026-05-15", evidence: checked(3, "2026-05-13"), paidAt: "2026-05-18" },
      { title: "A new roof: rafters, underlay and shingles", budget: m(24_400), funded: m(24_400), status: "paid", due: "2026-06-30", evidence: checked(4, "2026-06-27"), paidAt: "2026-07-02" },
      { title: "Double-glazed windows in 22 classrooms", budget: m(17_800), funded: m(17_800), status: "paid", due: "2026-08-20", evidence: checked(4, "2026-08-14"), paidAt: "2026-08-19" },
      { title: "Heating, paint and the first lessons", budget: m(12_200), funded: m(12_200), status: "paid", due: "2026-09-30", evidence: checked(4, "2026-09-26"), paidAt: "2026-10-01" },
    ],
    updates: [
      { date: "2026-10-01", text: "Complete: ₼12,200 released for the heating and the classrooms. 380 pupils started the term in warm, dry rooms." },
      { date: "2026-08-19", text: "₼17,800 released for the windows of 22 classrooms." },
      { date: "2026-07-02", text: "₼24,400 released for the new roof." },
      { date: "2026-05-18", text: "₼8,600 released for the scaffolding and taking the old roof off." },
    ],
  },
];

/* ---------------------------------------------------------------- derived figures */

export const goalOf = (p: Project): Qapik => p.milestones.reduce((s, x) => s + x.budget, 0);
export const raisedOf = (p: Project): Qapik => p.milestones.reduce((s, x) => s + x.funded, 0);
/** Paid to the contractor. */
export const releasedOf = (p: Project): Qapik =>
  p.milestones.filter((x) => x.status === "paid").reduce((s, x) => s + x.funded, 0);
/** Raised but not paid out yet: still in escrow (approved payments included until they land).
 *  A stopped project holds nothing: it gave the rest back. */
export const inEscrowOf = (p: Project): Qapik => (p.status === "stopped" ? 0 : raisedOf(p) - releasedOf(p));
/** What a stopped project gave back: refunded to cards, or moved to other projects. */
export const returnedOf = (p: Project): Qapik => (p.stop ? p.stop.refunded + p.stop.redirected : 0);
/** Outside Azerbaijan, so not on its map. */
export const isAbroad = (p: Project) => p.region === null;
/** The milestone the project is working on now: the first that is not paid. */
export const currentMilestone = (p: Project): number => {
  const i = p.milestones.findIndex((x) => x.status !== "paid");
  return i < 0 ? p.milestones.length - 1 : i;
};

const PROJECT_BY_ID = new Map(PROJECTS.map((p) => [p.id, p]));
const ORG_BY_ID = new Map(ORGANISATIONS.map((o) => [o.id, o]));

export const projectOf = (id: string | undefined | null) => (id ? PROJECT_BY_ID.get(id) : undefined);
export const organisationOf = (id: string | undefined | null) => (id ? ORG_BY_ID.get(id) : undefined);

export const projectsByCause = (cause: string) => PROJECTS.filter((p) => p.cause === cause);
export const projectsByRegion = (region: string) => PROJECTS.filter((p) => p.region === region);
export const projectsByOrg = (orgId: string) => PROJECTS.filter((p) => p.orgId === orgId);

export type RegionActivity = {
  /** Raised in the last 30 days, in qəpik. */
  raised: Qapik;
  donations: number;
  projects: number;
  organisations: number;
};

/** What the map shades: the last 30 days, per economic region. */
export function regionActivity(projects: Project[] = PROJECTS): Record<string, RegionActivity> {
  const out: Record<string, RegionActivity & { orgs: Set<string> }> = {};
  for (const p of projects) {
    if (p.region === null) continue; // abroad: not on the map of Azerbaijan
    const a = (out[p.region] ??= { raised: 0, donations: 0, projects: 0, organisations: 0, orgs: new Set() });
    a.raised += p.recent.raised;
    a.donations += p.recent.donations;
    a.projects += 1;
    a.orgs.add(p.orgId);
  }
  return Object.fromEntries(
    Object.entries(out).map(([k, { orgs, ...a }]) => [k, { ...a, organisations: orgs.size }])
  );
}

export function totals(projects: Project[] = PROJECTS) {
  return projects.reduce(
    (t, p) => ({
      raised: t.raised + raisedOf(p),
      released: t.released + releasedOf(p),
      inEscrow: t.inEscrow + inEscrowOf(p),
      donors: t.donors + p.donors,
      recentRaised: t.recentRaised + p.recent.raised,
      recentDonations: t.recentDonations + p.recent.donations,
    }),
    { raised: 0, released: 0, inEscrow: 0, donors: 0, recentRaised: 0, recentDonations: 0 }
  );
}
