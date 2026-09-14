/* Skater Page */

import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'
import SelectionButton from '../components/SelectionButton'
import '../styling/SelectionButton.css'
import '../styling/page.css'

export default function PlayerPage(){
    return (
        <>
            <div className="page-content">
                <h1 className='title'>Skater Stat Selection</h1>
                <h4 className='sub-title'>Select The Stat You Want To See</h4>
            </div>
            <div className='selection-button-center'>
                <div className='selection-button-wrapper'>
                    <SelectionButton label="Goals" to="/stats/skaters/goals"/>
                    <SelectionButton label="Assists" to="/stats/skaters/assists"/>
                    <SelectionButton label="Points" to="/stats/skaters/points"/>
                </div>
            </div>
            <div>
                <PreviousButton to ="/playerpage"/>
                <HomeButton to ="/"/>
            </div>
        </>
    )
}