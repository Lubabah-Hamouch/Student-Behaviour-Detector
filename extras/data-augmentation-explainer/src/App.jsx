
import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { ChevronRight, CheckCircle, AlertTriangle } from 'lucide-react';

const DataAugmentationExplanation = () => {
  const [language, setLanguage] = useState('en');
  const [activeStep, setActiveStep] = useState(0);

  // Data for visualizations
  const originalData = [
    { class: 'Concentrating', count: 2610, percentage: 61.1 },
    { class: 'Distracted', count: 647, percentage: 15.1 },
    { class: 'Hand Raised', count: 300, percentage: 7.0 },
    { class: 'Phone', count: 426, percentage: 10.0 },
    { class: 'Sleeping', count: 288, percentage: 6.7 }
  ];

  const balancedData = [
    { class: 'Concentrating', count: 4194, percentage: 57.0 },
    { class: 'Distracted', count: 1132, percentage: 15.4 },
    { class: 'Hand Raised', count: 674, percentage: 9.2 },
    { class: 'Phone', count: 806, percentage: 11.0 },
    { class: 'Sleeping', count: 553, percentage: 7.5 }
  ];

  const COLORS = ['#4ECDC4', '#FF6B6B', '#45B7D1', '#FFA07A', '#98D8C8'];

  const content = {
    en: {
      title: "Data Augmentation Strategy",
      subtitle: "How we balanced our student behavior dataset",
      problem: "The Problem",
      problemDesc: "Our original dataset was heavily imbalanced",
      solution: "The Solution",
      solutionDesc: "Two-level augmentation approach",
      results: "The Results",
      resultsDesc: "Balanced dataset with improved model performance",

      steps: [
        {
          title: "Original Dataset - Imbalanced",
          description: "We started with 430 manually annotated images containing 4,271 instances. The 'Concentrating' class dominated with 61.1%, while minority classes like 'Hand Raised' (7%) and 'Sleeping' (6.7%) were underrepresented.",
          problem: "This imbalance causes the model to be biased toward the majority class, poorly detecting minority behaviors."
        },
        {
          title: "Level 1: Targeted Augmentation (Albumentations)",
          description: "We applied realistic image transformations ONLY to minority classes to reach 55% of the majority class size. This created 164 new images saved to disk.",
          transformations: [
            "Lighting variations (±15% brightness/contrast)",
            "Realistic noise (simulating camera quality)",
            "Slight geometric shifts (±3% position, ±10% scale, ±2° rotation)",
            "JPEG compression simulation (75-95% quality)",
            "NO horizontal flipping (preserves classroom orientation)"
          ]
        },
        {
          title: "Level 2: Automatic YOLOv8 Augmentation",
          description: "During training, YOLOv8 applies additional augmentations ON-THE-FLY to ALL images at each epoch. These are NOT saved to disk.",
          transformations: [
            "Random rotation (max 10°)",
            "HSV color variations",
            "Horizontal flipping (50% probability)",
            "Translation (10%) and scaling (90%)",
            "Mosaic (combines 4 images)",
            "Mixup (blends images)",
            "Copy-paste (copies objects between images)"
          ]
        },
        {
          title: "Final Balanced Dataset",
          description: "After augmentation and cleaning, we obtained 725 high-quality images with 7,359 instances. The imbalance ratio improved from 9.1:1 to 2.9:1 (68% reduction).",
          improvements: [
            "Total images: 430 → 725 (+69%)",
            "Total instances: 4,271 → 7,359 (+72%)",
            "Imbalance ratio: 9.1:1 → 2.9:1 (-68%)",
            "All classes now adequately represented"
          ]
        }
      ],

      keyPoints: {
        title: "Key Points",
        points: [
          "We used TWO complementary augmentation strategies",
          "Level 1 creates PERMANENT new images for minority classes",
          "Level 2 applies TEMPORARY augmentations during training",
          "All transformations are REALISTIC (simulate real classroom conditions)",
          "Bounding boxes are automatically adjusted and validated"
        ]
      },

      whyItWorks: {
        title: "Why This Approach Works",
        reasons: [
          "Model sees more examples of rare behaviors (hand raised, sleeping)",
          "Realistic augmentations improve model robustness to lighting, angles, camera quality",
          "Two-level strategy prevents overfitting while maintaining diversity",
          "Balanced dataset = fair learning for all classes"
        ]
      }
    },

    fr: {
      title: "Stratégie d'Augmentation de Données",
      subtitle: "Comment nous avons équilibré notre dataset de comportements étudiants",
      problem: "Le Problème",
      problemDesc: "Notre dataset original était fortement déséquilibré",
      solution: "La Solution",
      solutionDesc: "Approche d'augmentation à deux niveaux",
      results: "Les Résultats",
      resultsDesc: "Dataset équilibré avec performance améliorée du modèle",

      steps: [
        {
          title: "Dataset Original - Déséquilibré",
          description: "Nous avons commencé avec 430 images annotées manuellement contenant 4 271 instances. La classe 'Concentré' dominait avec 61,1%, tandis que les classes minoritaires comme 'Main Levée' (7%) et 'Endormi' (6,7%) étaient sous-représentées.",
          problem: "Ce déséquilibre fait que le modèle est biaisé vers la classe majoritaire et détecte mal les comportements minoritaires."
        },
        {
          title: "Niveau 1 : Augmentation Ciblée (Albumentations)",
          description: "Nous avons appliqué des transformations réalistes UNIQUEMENT aux classes minoritaires pour atteindre 55% de la taille de la classe majoritaire. Cela a créé 164 nouvelles images sauvegardées sur disque.",
          transformations: [
            "Variations d'éclairage (±15% luminosité/contraste)",
            "Bruit réaliste (simulant la qualité caméra)",
            "Légers déplacements géométriques (±3% position, ±10% échelle, ±2° rotation)",
            "Simulation de compression JPEG (75-95% qualité)",
            "PAS de retournement horizontal (préserve l'orientation de la classe)"
          ]
        },
        {
          title: "Niveau 2 : Augmentation Automatique YOLOv8",
          description: "Pendant l'entraînement, YOLOv8 applique des augmentations supplémentaires À LA VOLÉE sur TOUTES les images à chaque epoch. Celles-ci ne sont PAS sauvegardées sur disque.",
          transformations: [
            "Rotation aléatoire (max 10°)",
            "Variations de couleur HSV",
            "Retournement horizontal (50% probabilité)",
            "Translation (10%) et mise à l'échelle (90%)",
            "Mosaïque (combine 4 images)",
            "Mixup (mélange d'images)",
            "Copy-paste (copie d'objets entre images)"
          ]
        },
        {
          title: "Dataset Final Équilibré",
          description: "Après augmentation et nettoyage, nous avons obtenu 725 images de haute qualité avec 7 359 instances. Le ratio de déséquilibre s'est amélioré de 9,1:1 à 2,9:1 (réduction de 68%).",
          improvements: [
            "Total d'images : 430 → 725 (+69%)",
            "Total d'instances : 4 271 → 7 359 (+72%)",
            "Ratio de déséquilibre : 9,1:1 → 2,9:1 (-68%)",
            "Toutes les classes maintenant adéquatement représentées"
          ]
        }
      ],

      keyPoints: {
        title: "Points Clés",
        points: [
          "Nous avons utilisé DEUX stratégies d'augmentation complémentaires",
          "Le Niveau 1 crée de NOUVELLES images PERMANENTES pour les classes minoritaires",
          "Le Niveau 2 applique des augmentations TEMPORAIRES pendant l'entraînement",
          "Toutes les transformations sont RÉALISTES (simulent de vraies conditions de classe)",
          "Les boîtes englobantes sont automatiquement ajustées et validées"
        ]
      },

      whyItWorks: {
        title: "Pourquoi Cette Approche Fonctionne",
        reasons: [
          "Le modèle voit plus d'exemples de comportements rares (main levée, endormi)",
          "Les augmentations réalistes améliorent la robustesse du modèle à l'éclairage, aux angles, à la qualité caméra",
          "La stratégie à deux niveaux prévient le surapprentissage tout en maintenant la diversité",
          "Dataset équilibré = apprentissage équitable pour toutes les classes"
        ]
      }
    }
  };

  const t = content[language];

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 text-white p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold mb-4 bg-gradient-to-r from-green-400 to-blue-500 bg-clip-text text-transparent">
            {t.title}
          </h1>
          <p className="text-xl text-gray-300 mb-6">{t.subtitle}</p>

          {/* Language Toggle */}
          <div className="inline-flex rounded-lg border border-gray-600 p-1 bg-gray-800">
            <button
              onClick={() => setLanguage('en')}
              className={`px-6 py-2 rounded-md transition-all ${
                language === 'en' ? 'bg-green-500 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              English
            </button>
            <button
              onClick={() => setLanguage('fr')}
              className={`px-6 py-2 rounded-md transition-all ${
                language === 'fr' ? 'bg-green-500 text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              Français
            </button>
          </div>
        </div>

        {/* Progress Indicator */}
        <div className="mb-12">
          <div className="flex justify-between items-center">
            {t.steps.map((step, idx) => (
              <React.Fragment key={idx}>
                <div
                  onClick={() => setActiveStep(idx)}
                  className={`cursor-pointer transition-all ${
                    activeStep === idx ? 'scale-110' : 'opacity-50 hover:opacity-75'
                  }`}
                >
                  <div className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl font-bold ${
                    activeStep === idx ? 'bg-green-500' : 'bg-gray-700'
                  }`}>
                    {idx + 1}
                  </div>
                  <p className="text-xs text-center mt-2 max-w-[100px]">{step.title.split(' - ')[0]}</p>
                </div>
                {idx < t.steps.length - 1 && (
                  <div className={`flex-1 h-1 mx-4 ${
                    activeStep > idx ? 'bg-green-500' : 'bg-gray-700'
                  }`} />
                )}
              </React.Fragment>
            ))}
          </div>
        </div>

        {/* Main Content */}
        <div className="bg-gray-800 rounded-2xl p-8 mb-8 shadow-2xl">
          <h2 className="text-3xl font-bold mb-4 text-green-400">
            {t.steps[activeStep].title}
          </h2>
          <p className="text-lg text-gray-300 mb-6 leading-relaxed">
            {t.steps[activeStep].description}
          </p>

          {/* Step-specific content */}
          {activeStep === 0 && (
            <div>
              <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4 mb-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="text-red-400 mt-1" size={24} />
                  <p className="text-red-300">{t.steps[0].problem}</p>
                </div>
              </div>

              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={originalData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="class" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                    labelStyle={{ color: '#F3F4F6' }}
                  />
                  <Bar dataKey="count" fill="#FF6B6B" />
                </BarChart>
              </ResponsiveContainer>

              <div className="mt-6 grid grid-cols-2 gap-4">
                <div className="bg-gray-700 rounded-lg p-4">
                  <p className="text-sm text-gray-400 mb-2">{language === 'en' ? 'Total Images' : "Total d'Images"}</p>
                  <p className="text-3xl font-bold text-green-400">430</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-4">
                  <p className="text-sm text-gray-400 mb-2">{language === 'en' ? 'Imbalance Ratio' : 'Ratio de Déséquilibre'}</p>
                  <p className="text-3xl font-bold text-red-400">9.1:1</p>
                </div>
              </div>
            </div>
          )}

          {(activeStep === 1 || activeStep === 2) && (
            <div>
              <h3 className="text-xl font-semibold mb-4 text-blue-400">
                {language === 'en' ? 'Transformations Applied:' : 'Transformations Appliquées :'}
              </h3>
              <ul className="space-y-3">
                {t.steps[activeStep].transformations.map((trans, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-gray-300">
                    <CheckCircle className="text-green-400 mt-1 flex-shrink-0" size={20} />
                    <span>{trans}</span>
                  </li>
                ))}
              </ul>

              {activeStep === 1 && (
                <div className="mt-6 bg-blue-900/20 border border-blue-500/50 rounded-lg p-4">
                  <p className="text-blue-300">
                    <strong>{language === 'en' ? 'Result:' : 'Résultat :'}</strong> {language === 'en' ? '164 new images created and saved to disk' : '164 nouvelles images créées et sauvegardées sur disque'}
                  </p>
                </div>
              )}
            </div>
          )}

          {activeStep === 3 && (
            <div>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={balancedData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="class" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                    labelStyle={{ color: '#F3F4F6' }}
                  />
                  <Bar dataKey="count" fill="#4ECDC4" />
                </BarChart>
              </ResponsiveContainer>

              <div className="mt-6 grid grid-cols-3 gap-4">
                <div className="bg-gray-700 rounded-lg p-4">
                  <p className="text-sm text-gray-400 mb-2">{language === 'en' ? 'Total Images' : "Total d'Images"}</p>
                  <p className="text-3xl font-bold text-green-400">725</p>
                  <p className="text-sm text-green-300">+69%</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-4">
                  <p className="text-sm text-gray-400 mb-2">{language === 'en' ? 'Total Instances' : "Total d'Instances"}</p>
                  <p className="text-3xl font-bold text-green-400">7,359</p>
                  <p className="text-sm text-green-300">+72%</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-4">
                  <p className="text-sm text-gray-400 mb-2">{language === 'en' ? 'Imbalance Ratio' : 'Ratio de Déséquilibre'}</p>
                  <p className="text-3xl font-bold text-green-400">2.9:1</p>
                  <p className="text-sm text-green-300">-68%</p>
                </div>
              </div>

              <div className="mt-6">
                <h3 className="text-xl font-semibold mb-4 text-green-400">
                  {language === 'en' ? 'Improvements:' : 'Améliorations :'}
                </h3>
                <ul className="space-y-3">
                  {t.steps[3].improvements.map((imp, idx) => (
                    <li key={idx} className="flex items-start gap-3 text-gray-300">
                      <CheckCircle className="text-green-400 mt-1 flex-shrink-0" size={20} />
                      <span>{imp}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Navigation */}
          <div className="flex justify-between mt-8">
            <button
              onClick={() => setActiveStep(Math.max(0, activeStep - 1))}
              disabled={activeStep === 0}
              className="px-6 py-3 bg-gray-700 rounded-lg disabled:opacity-30 hover:bg-gray-600 transition-all"
            >
              {language === 'en' ? '← Previous' : '← Précédent'}
            </button>
            <button
              onClick={() => setActiveStep(Math.min(t.steps.length - 1, activeStep + 1))}
              disabled={activeStep === t.steps.length - 1}
              className="px-6 py-3 bg-green-500 rounded-lg disabled:opacity-30 hover:bg-green-600 transition-all"
            >
              {language === 'en' ? 'Next →' : 'Suivant →'}
            </button>
          </div>
        </div>

        {/* Key Points Section */}
        <div className="grid md:grid-cols-2 gap-8">
          <div className="bg-gradient-to-br from-blue-900/30 to-blue-800/30 rounded-2xl p-6 border border-blue-500/30">
            <h3 className="text-2xl font-bold mb-4 text-blue-400">{t.keyPoints.title}</h3>
            <ul className="space-y-3">
              {t.keyPoints.points.map((point, idx) => (
                <li key={idx} className="flex items-start gap-3 text-gray-300">
                  <ChevronRight className="text-blue-400 mt-1 flex-shrink-0" size={20} />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-gradient-to-br from-green-900/30 to-green-800/30 rounded-2xl p-6 border border-green-500/30">
            <h3 className="text-2xl font-bold mb-4 text-green-400">{t.whyItWorks.title}</h3>
            <ul className="space-y-3">
              {t.whyItWorks.reasons.map((reason, idx) => (
                <li key={idx} className="flex items-start gap-3 text-gray-300">
                  <CheckCircle className="text-green-400 mt-1 flex-shrink-0" size={20} />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DataAugmentationExplanation;
