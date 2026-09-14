/* Previous Button Component */

import { Link } from 'react-router-dom'
import '../styling/previousButton.css'
import { HiOutlineArrowSmLeft } from "react-icons/hi";

export default function PreviousButton({to}){
    return (
        <>
            <Link to={to} className='previous-button'>
                <HiOutlineArrowSmLeft size={42}/>
            </Link>
        </>
    )
}