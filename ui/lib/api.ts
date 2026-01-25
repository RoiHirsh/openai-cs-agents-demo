// Fetch ChatKit thread state for the Agent panel
export async function fetchThreadState(threadId: string) {
  try {
    const res = await fetch(`/chatkit/state?thread_id=${encodeURIComponent(threadId)}`);
    if (!res.ok) throw new Error(`State API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error fetching thread state:", err);
    return null;
  }
}

export async function fetchBootstrapState(leadInfo?: {
  first_name?: string;
  email?: string;
  phone?: string;
  country?: string;
  new_lead?: boolean;
}) {
  try {
    const params = new URLSearchParams();
    if (leadInfo) {
      if (leadInfo.first_name) params.append("first_name", leadInfo.first_name);
      if (leadInfo.email) params.append("email", leadInfo.email);
      if (leadInfo.phone) params.append("phone", leadInfo.phone);
      if (leadInfo.country) params.append("country", leadInfo.country);
      if (leadInfo.new_lead !== undefined) params.append("new_lead", String(leadInfo.new_lead));
    }
    const url = `/chatkit/bootstrap${params.toString() ? `?${params.toString()}` : ""}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Bootstrap API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error bootstrapping state:", err);
    return null;
  }
}
