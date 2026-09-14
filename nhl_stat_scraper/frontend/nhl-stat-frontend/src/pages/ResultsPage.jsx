/* Results Page */

import { useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import '../styling/page.css'
import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'

export default function ResultsPage(){
    const { state } = useLocation();
    const { playerType, statType, statKey, count, gameType } = state;

    const [results, setResults] = useState(null);


    useEffect(() => {
        console.log("FETCHING:", { playerType, statType, count, gameType });
        
        const fetchData = async () => {
            const url = `https://nhl-web-scraping.onrender.com/stats/${playerType}/${statType}?count=${count}&gameType=${encodeURIComponent(gameType)}`;
            try {
                const res = await fetch(url);
                const data = await res.json();
                setResults(data);
            } catch (err) {
                console.error("API error: ", err);
            }
        };

        fetchData();
    }, [playerType, statType, count, gameType]);

    return(
        <>
            <div className="page-content">
                <h1 className='title'>Results</h1>
                <h4 className="sub-title">View Your Results</h4>
            </div>
            <HomeButton />
            <PreviousButton to={`/stats/${playerType}/${statType}`} />

            <div className="results-list">
                {results ? (
                    <>
                        <h3 className='title'>{results.title}</h3>
                        <ol>
                        {results.leaders.map((player, i) => (
                            <li key={i} className='result-row'>
                                <span className="result-rank">{i + 1}.</span>
                                <span className="result-text">{player.name}: {player[statKey]}</span>
                            </li>
                        ))}
                        </ol>
                    </>
                ) : (
                    <p className='loading'>Loading results...</p>
                )}
            </div>            
        </>
    )
}