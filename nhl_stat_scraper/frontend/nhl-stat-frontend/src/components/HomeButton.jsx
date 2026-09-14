/* Home Button Component */

import { Link } from 'react-router-dom'
import '../styling/homeButton.css'
import { FaHome } from "react-icons/fa";

export default function HomeButton(){
    return (
        <>
            <Link to="/" className='home-button'>
                <FaHome size={32} />
            </Link>
        </>
    )
}