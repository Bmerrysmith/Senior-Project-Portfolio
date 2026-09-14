/* Selection Buttons Component */

import { Link } from 'react-router-dom'
import '../styling/SelectionButton.css'


export default function SelectionButton({label, to}){
    return (
        <Link to={to} >
            <button className="selection-button">
                {label}
            </button>
            </Link>
    )
}