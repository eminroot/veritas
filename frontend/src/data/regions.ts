import { REGION_SHAPES, type RegionShape } from "@/components/map/az-regions";

/**
 * Azerbaijan's 14 economic regions (the 2021 division), the unit the donation map shades.
 * The shapes and district lists live in components/map/az-regions.ts, generated from
 * open boundary data; this file only adds what the pages say about each region.
 */
export type RegionKey =
  | "baku"
  | "absheron-khizi"
  | "mountainous-shirvan"
  | "ganja-dashkasan"
  | "karabakh"
  | "gazakh-tovuz"
  | "guba-khachmaz"
  | "lankaran-astara"
  | "central-aran"
  | "mil-mughan"
  | "shaki-zagatala"
  | "east-zangezur"
  | "shirvan-salyan"
  | "nakhchivan";

export type Region = RegionShape & { key: RegionKey };

export const REGIONS: Region[] = REGION_SHAPES as Region[];

const BY_KEY = new Map(REGIONS.map((r) => [r.key, r]));

export function regionOf(key: string | undefined | null): Region | undefined {
  return key ? BY_KEY.get(key as RegionKey) : undefined;
}
