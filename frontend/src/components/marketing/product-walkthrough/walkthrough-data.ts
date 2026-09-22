export const DEMO_FILE = {
  name: "service-history-demo.csv",
  rows: 248,
  fields: ["job_id", "service_date", "location", "equipment", "issue", "duration"],
} as const;

export const DEMO_JOBS = {
  original: {
    id: "ST-1048",
    date: "Jun 12",
    customer: "Cedar Lane Dental",
    location: "14 Cedar Lane",
    equipment: "RTU-2 · Lennox LGA090",
    issue: "No cooling in east treatment rooms",
    note: "Investigated cooling issue and cleared condensate drain.",
  },
  returnVisit: {
    id: "ST-1071",
    date: "Jun 18",
    customer: "Cedar Lane Dental",
    location: "14 Cedar Lane",
    equipment: "RTU-2 · Lennox LGA090",
    issue: "Cooling issue in east treatment rooms",
    note: "Cooling issue reported again; inspected the same unit.",
  },
} as const;

export const DEMO_QUEUE = [
  {
    id: "ST-1071",
    account: "Cedar Lane Dental",
    issue: "No cooling · RTU-2",
    interval: "6 days",
    status: "Possible callback",
    highlighted: true,
  },
  {
    id: "ST-1094",
    account: "Harbor Print Co.",
    issue: "Airflow · AHU-1",
    interval: "12 days",
    status: "Needs review",
    highlighted: false,
  },
  {
    id: "ST-1102",
    account: "Mason Street Market",
    issue: "Thermostat · Unit 4",
    interval: "18 days",
    status: "Needs review",
    highlighted: false,
  },
] as const;

export const EVIDENCE = [
  { label: "Same location", detail: "14 Cedar Lane", strength: "+15" },
  { label: "Same equipment", detail: "RTU-2 · Lennox LGA090", strength: "+30" },
  { label: "Short interval", detail: "6 calendar days", strength: "+25" },
  { label: "Similar issue description", detail: "Cooling complaint", strength: "+20" },
] as const;

export const COST_LINES = [
  { label: "Labor", input: "2.5 hr × $48/hr", amount: "$120" },
  { label: "Vehicle dispatch", input: "per return visit", amount: "$35" },
  { label: "Overhead", input: "per return visit", amount: "$30" },
  { label: "Opportunity", input: "2.5 hr × $70/hr", amount: "$175" },
  { label: "Parts", input: "return-visit line items", amount: "$64" },
] as const;

export const ESTIMATED_TOTAL = "$424";
