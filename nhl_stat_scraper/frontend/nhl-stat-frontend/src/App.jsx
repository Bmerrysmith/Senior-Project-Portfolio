/* App.jsx */

import { BrowserRouter, Routes, Route } from 'react-router-dom'
import AssistStatPage from "./pages/AssistStatPage.jsx";
import GoaliePage from "./pages/GoaliePage.jsx";
import GoalStatPage from "./pages/GoalStatPage.jsx";
import HomePage from "./pages/Home.jsx"
import PlayerPage from "./pages/PlayerPage.jsx"
import PointStatPage from "./pages/PointsStatPage.jsx";
import SkaterPage from "./pages/SkaterPage.jsx"
import SvStatPage from "./pages/SvStatPage.jsx";
import GaaStatPage from "./pages/GaaStatPage.jsx";
import SoStatPage from "./pages/SoStatPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";

export default function App() {
  return (
    <>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/playerpage" element={<PlayerPage />} />
          <Route path="/skaters" element={<SkaterPage />} />
          <Route path="/goalies" element={<GoaliePage />} />

          <Route path="/stats/skaters/goals" element={<GoalStatPage />} />
          <Route path="/stats/skaters/assists" element={<AssistStatPage />} />
          <Route path="/stats/skaters/points" element={<PointStatPage />} />

          <Route path="/stats/goalies/sv" element={<SvStatPage />} />
          <Route path="/stats/goalies/gaa" element={<GaaStatPage />} />
          <Route path="/stats/goalies/so" element={<SoStatPage />} />

          <Route path="/results/:playerType/:statType" element={<ResultsPage />} />

        </Routes>
      </BrowserRouter>
      
    </>
  );
}