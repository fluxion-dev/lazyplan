import { Faq } from "./components/site/faq"
import { FeatureMatrix } from "./components/site/feature-matrix"
import { Footer } from "./components/site/footer"
import { GetStarted } from "./components/site/get-started"
import { Header } from "./components/site/header"
import { Hero } from "./components/site/hero"
import { HowItWorks } from "./components/site/how-it-works"
import { InstallCommand } from "./components/site/install-command"
import { LeadStory } from "./components/site/lead-story"
import { ProofSection } from "./components/site/proof-section"
import { Screenshots } from "./components/site/screenshots"
import { WaysToWork } from "./components/site/ways-to-work"

export default function App() {
  return (
    <div className="min-h-svh">
      <Header />
      <Hero />
      <main id="main">
        <InstallCommand />
        <LeadStory />
        <FeatureMatrix />
        <WaysToWork />
        <ProofSection />
        <Screenshots />
        <HowItWorks />
        <Faq />
        <GetStarted />
      </main>
      <Footer />
    </div>
  )
}
