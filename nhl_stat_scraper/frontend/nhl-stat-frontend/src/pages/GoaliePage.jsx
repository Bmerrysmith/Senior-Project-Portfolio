/* Goalie Page */

import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'
import SelectionButton from '../components/SelectionButton'
import '../styling/SelectionButton.css'
import '../styling/page.css'

export default function GoaliePage(){
    return (
        <>
            <div className="page-content">
                <h1 className='title'>Goalie Stat Selection</h1>
                <h4 className='sub-title'>Select The Stat You Want To See</h4>
            </div>
            <div className='selection-button-center'>
                <div className='selection-button-wrapper'>
                    <SelectionButton label="Save Percentage" to="/stats/goalies/sv"/>
                    <SelectionButton label="Goals Against Average" to="/stats/goalies/gaa"/>
                    <SelectionButton label="Shutouts" to="/stats/goalies/so"/>
                </div>
            </div>
            <div>
                <PreviousButton to ="/PlayerPage"/>
                <HomeButton to ="/"/>
            </div>
        </>
    )
}