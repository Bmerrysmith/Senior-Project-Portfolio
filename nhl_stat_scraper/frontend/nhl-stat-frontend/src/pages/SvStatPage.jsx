/* SV Stat Page */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styling/page.css'
import PageInput from '../components/PageInput'
import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'

export default function SvStatPage(){
    const [count, setCount] = useState(10);
    const [gameType, setGameType] = useState("Regular Season");

    const navigate = useNavigate();

    const handleSeeResults = () => {
        console.log({ count, gameType });
        navigate("/results/goalies/sv", {
                state: {
                playerType: "goalies",
                statType: "sv",
                statKey: "save_percentage",
                count,
                gameType
                }
            });
        };


    return(
        <>
            <div className="page-content">
                <h1 className='title'>Top Goalies - Save Percentage</h1>
                <h4 className='sub-title'>Select The Number of Goalies and Season Type</h4>
            </div>
            <HomeButton />
            <PreviousButton to="/goalies" />
            <PageInput 
                playerType="Goalies" 
                stat="Save Percentage" 
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