/* Number and Season Input Component */

import { useState, useEffect } from "react";
import '../styling/pageInput.css'

export default function PageInput({playerType, stat, onCountChange, onGameTypeChange}){
    const [listNum , setListNum] = useState("10");
    const [seasonType, setSeasonType] = useState("Regular Season");

    useEffect(() => {
        onCountChange?.(parseInt(listNum));
    }, [listNum]);

    useEffect(() => {
        onGameTypeChange?.(seasonType);
    }, [seasonType]);
    
    return(
        <>
            <div className="control-row">
                <label className="number-input">
                    Number of {playerType} (1-50): 
                    <input 
                        className="number-content"
                        name="numValue" 
                        type="number" 
                        min={1} 
                        max={50} 
                        value={listNum}
                        onChange={(e) => {
                            const val = e.target.value;

                            
                            if (val === "" || (/^\d{0,2}$/.test(val))) {
                                setListNum(val);
                            }
                        }}
                        onBlur={() => {
                            const num = Number(listNum);
                            const clamped = Math.max(1, Math.min(num || 1, 50));
                            setListNum(clamped.toString());
                        }}

                    />
                </label>

                <p className="radio-input">
                    Season Type: 
                    <label className="radio-option">
                        Regular Season
                        <input 
                            name="seasonType"
                            type="radio"
                            value={"Regular Season"}
                            defaultChecked={true}
                            onChange={(e) => setSeasonType(e.target.value)}
                        />
                    </label>
                    <label className="radio-option">
                        Playoffs
                        <input 
                            name="seasonType"
                            type="radio"
                            value={"Playoffs"}
                            onChange={(e) => setSeasonType(e.target.value)}
                        />
                    </label>
                </p>
            </div>
            
            <p className="page-summary">Top {listNum} {playerType} By {stat} for The {seasonType} Are Selected</p>
        </>
    )
   
}