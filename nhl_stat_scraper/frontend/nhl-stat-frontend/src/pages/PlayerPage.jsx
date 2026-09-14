/* Player Page */

import HomeButton from '../components/HomeButton'
import PreviousButton from '../components/PreviousButton'
import SelectionButton from '../components/SelectionButton'
import '../styling/SelectionButton.css'
import '../styling/page.css'

export default function PlayerPage(){
    return (
        <>
            <div className="page-content">
                <h1 className='title'>Player Selection</h1>
                <h4 className='sub-title'>Select The Type of Player You Want To See</h4>
            </div>
            <div className='selection-button-center'>
                <div className='selection-button-wrapper'>
                    <SelectionButton label="Skaters" to="/skaters"/>
                    <SelectionButton label="Goalies" to="/goalies"/>
                </div>
            </div>
            <div>
                <PreviousButton to ="/"/>
                <HomeButton to ="/"/>
            </div>
        </>
    )
}