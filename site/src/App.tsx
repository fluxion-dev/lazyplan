import { Faq } from "./components/site/faq"
import { Features, WhatsNew } from "./components/site/whats-new"
import { Footer } from "./components/site/footer"
import { GetStarted } from "./components/site/get-started"
import { Header } from "./components/site/header"
import { Hero } from "./components/site/hero"
import { HowItWorks } from "./components/site/how-it-works"
import { InstallCommand } from "./components/site/install-command"
import { Screenshots } from "./components/site/screenshots"
import { WaysToWork } from "./components/site/ways-to-work"

export default function App() {
  return (
    <div className="min-h-svh">
      <Header />
      <Hero />
      <main id="main">
        <InstallCommand />
        <WhatsNew />
        <Features />
        <WaysToWork />
        <Screenshots />
        <HowItWorks />
        <Faq />
        <GetStarted />
      </main>
      <Footer />
    </div>
  )
}
