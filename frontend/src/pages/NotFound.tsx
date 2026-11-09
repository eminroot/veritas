import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { Compass } from "lucide-react";
import { LpHero, LpPage } from "@/components/lp/LpChrome";
import { Btn, Eyebrow } from "@/components/lp/primitives";

export default function NotFound() {
  const location = useLocation();

  useEffect(() => {
    console.error("404: nothing at", location.pathname);
  }, [location.pathname]);

  return (
    <LpPage>
      <LpHero
        eyebrow={<Eyebrow icon={Compass}>404 · {location.pathname}</Eyebrow>}
        title="Nothing is built here yet."
        lead="The address may be mistyped, or the project has moved. Every cause is one click away."
      >
        <Btn to="/donate" label="Browse causes" size="lg" />
        <Btn to="/" label="Back to home" variant="quiet" size="lg" />
      </LpHero>
    </LpPage>
  );
}
