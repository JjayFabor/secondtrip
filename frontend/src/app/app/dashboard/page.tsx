import type { Metadata } from "next";

import { DashboardHome } from "@/components/dashboard/dashboard-home";

export const metadata: Metadata = {
  title: "Overview — SecondTrip",
};

export default function DashboardPage() {
  return <DashboardHome />;
}
