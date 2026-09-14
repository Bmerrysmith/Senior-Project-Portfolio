/* Home Page */
import SelectionButton from '../components/SelectionButton'
import '../styling/home.css'

export default function HomePage(){
    return (
        <div className="home-container">
            <div className="home-content">
                <h1 className='title'>NHL Stat Web Scraper</h1>
                <h4 className='sub-title'></h4> 
                <h4 className='sub-title'></h4> 
                <h4 className='sub-title'></h4> 
                <div className='selection-button-center'>
                    <div className='selection-button-wrapper'>
                        <SelectionButton label="Get Started" to="/playerpage" />
                    </div>  
                </div> 
            </div>
        </div>
    )
}
