// API service for router-related operations
const API_BASE_URL = "http://localhost:5000"; // Update this with your Flask server URL

export const getRouterInfo = async (routerId) => {
  try {
    const response = await fetch(`${API_BASE_URL}/get_router/${routerId}`);
    if (!response.ok) {
      throw new Error("Failed to fetch router information");
    }
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error fetching router information:", error);
    throw error;
  }
};

export const getRouterStatus = async (routerId) => {
  try {
    const response = await fetch(
      `${API_BASE_URL}/get_router_status/${routerId}`
    );
    if (!response.ok) {
      throw new Error("Failed to fetch router status");
    }
    const data = await response.json();
    return data;
  } catch (error) {
    console.error("Error fetching router status:", error);
    throw error;
  }
};
