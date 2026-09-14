/* Points Stat Page */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styling/page.css'
import PageInput from '../components/PageInput'
import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'

export default function PointStatPage(){
    const [count, setCount] = useState(10);
    const [gameType, setGameType] = useState("Regular Season");

    const navigate = useNavigate();

    const handleSeeResults = () => {
        navigate("/results/skaters/points", {
                state: {
                playerType: "skaters",
                statType: "points",
                statKey: "points",
                count,
                gameType
                }
            });
        };


    return(
        <>
            <div className="page-content">
                <h1 className='title'>Top Skaters - Points</h1>
                <h4 className='sub-title'>Select The Number of Skaters and Season Type</h4>
            </div>
            <HomeButton />
            <PreviousButton to="/skaters" />
            <PageInput 
                playerType="Skaters" 
                stat="Points" 
                onCountChange={setCount}
                onGameTypeChange={setGameType}
            />
            <div className='selection-button-center'>
                <div className='selection-button-wrapper'>
                    <button className='selection-button' onClick={handleSeeResults}>
                        See Results    
                    </button>     
                </div>
            </div>
        </>
    )
}